import subprocess
import time
import socket
import json
import threading
import sys
import select
import argparse
from statistics import mean
import csv

MULTICAST_GROUP_FIREWORKS = "224.0.0.1"
MULTICAST_GROUP_ROUND_TIMES = "224.1.1.1"
MULTICAST_PORT_FIREWORKS = 5007
MULTICAST_PORT_ROUND_TIMES = 5008
BASE_PORT = 5000
MAX_WAIT_TIME = 60
CSV_FILE = "multidevice_experiment_results.csv"


def listen_for_multicasts(stop_event, round_times, multicast_count):
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
                        round_times.append(message["duration"])

                elif ready_sock == sock_firework:
                    # Firework message
                    if "Firework from" in message:
                        print(message)
                        multicast_count[0] += 1

        except socket.timeout:
            continue
        except Exception as e:
            print("Error receiving multicast:", e)

    sock_round_time.close()
    sock_firework.close()


def writeStats(results):
    fieldnames = ["n", "rounds", "multicasts", "min_time", "max_time", "avg_time"]
    with open(CSV_FILE, mode="w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=",")
        writer.writeheader()
        writer.writerow(results)


def run_single_ring(args):
    round_times = []
    multicast_count = [0]

    stop_event = threading.Event()
    listener = threading.Thread(
        target=listen_for_multicasts, args=(stop_event, round_times, multicast_count)
    )

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

        start_time = time.time()
        while proc.poll() is None:
            if time.time() - start_time > MAX_WAIT_TIME:
                print("Process timed out")
                proc.terminate()
                break
            time.sleep(1)

        time.sleep(2)  # Let the process start

        print("multicast_count:", multicast_count[0])
        print("round_times:", round_times)
        if proc.returncode == 0:
            print("Process completed successfully")
            if round_times:
                results = {
                    "n": 2,  # Assuming 2 machines in the ring
                    "rounds": len(round_times),
                    "multicasts": multicast_count[0],
                    "min_time": min(round_times),
                    "max_time": max(round_times),
                    "avg_time": mean(round_times),
                }
                print("\nExperiment Results:")
                for key, value in results.items():
                    print(f"{key}: {value}")
                writeStats(results)
            else:
                print("No data collected")
                return None
        else:
            print(f"Process failed with return code {proc.returncode}")
            return None

    except Exception as e:
        print(f"Error: {e}")
        return None

    finally:
        # Cleanup
        stop_event.set()
        listener.join()

        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default=None, required=True)
    parser.add_argument("--next_host", type=str, default=None)
    run_single_ring(parser.parse_args())
