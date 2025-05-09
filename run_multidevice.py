import subprocess
import time
import socket
import json
import threading
import sys
import select
import argparse

MULTICAST_GROUP_FIREWORKS = "224.0.0.1"
MULTICAST_GROUP_ROUND_TIMES = "224.1.1.1"
MULTICAST_PORT_FIREWORKS = 5007
MULTICAST_PORT_ROUND_TIMES = 5008
BASE_PORT = 5000
MAX_WAIT_TIME = 60


def listen_for_multicasts(stop_event):
    # Listen for round time messages
    sock_round_time = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_round_time.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock_round_time.bind(("", MULTICAST_PORT_ROUND_TIMES))
    group_round_time = socket.inet_aton(MULTICAST_GROUP_ROUND_TIMES)
    mreq_round_time = group_round_time + socket.inet_aton("0.0.0.0")
    sock_round_time.setsockopt(
        socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq_round_time
    )
    sock_round_time.settimeout(1.0)

    # Listen for firework messages
    sock_firework = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_firework.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock_firework.bind(("", MULTICAST_PORT_FIREWORKS))
    group_firework = socket.inet_aton(MULTICAST_GROUP_FIREWORKS)
    mreq_firework = group_firework + socket.inet_aton("0.0.0.0")
    sock_firework.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq_firework)
    sock_firework.settimeout(1.0)

    # Listen for multicasts from the process
    while not stop_event.is_set():
        try:
            ready_to_read, _, _ = select.select(
                [sock_round_time, sock_firework], [], [], 1.0
            )
            for ready_sock in ready_to_read:
                data, _ = ready_sock.recvfrom(1024)
                message = data.decode()
                if ready_sock == sock_round_time:
                    # Round time message
                    message = json.loads(message)
                    if message.get("type") == "round_time":
                        print(f"Round Time: {message['duration']:.6f} seconds")
                elif ready_sock == sock_firework:
                    # Firework message
                    if "Firework from" in message:
                        print(message)

        except socket.timeout:
            continue
        except Exception as e:
            print("Error receiving multicast:", e)

    sock_round_time.close()
    sock_firework.close()


def run_single_ring(args):
    processes = []

    stop_event = threading.Event()
    listener = threading.Thread(target=listen_for_multicasts, args=(stop_event,))
    listener.start()

    try:
        # Start the first process (only process 0)
        proc = subprocess.Popen(
            [
                sys.executable,
                "process.py",
                "--id",
                "0",
                "--next_host",
                args.next_host,
                "--inject_token",
            ]
        )
        processes.append(proc)

        time.sleep(2)  # Let the process start

        # Wait for the listener to capture multicasts
        time.sleep(MAX_WAIT_TIME)

    except Exception as e:
        print(f"Error: {e}")

    finally:
        # Cleanup
        stop_event.set()
        listener.join()

        for proc in processes:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default=None, required=True)
    parser.add_argument("--next_host", type=str, default=None)
    run_single_ring(parser.parse_args())
