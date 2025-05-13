import subprocess
import time
import socket
import json
import threading
from statistics import mean
import sys
import csv
import select

MULTICAST_GROUP_FIREWORKS = "224.0.0.1"
MULTICAST_GROUP = "224.1.1.1"
MULTICAST_PORT_FIREWORKS = 5007
MULTICAST_PORT_ROUND_TIMES = 5008
BASE_PORT = 6000
MAX_WAIT_TIME = 60
CSV_FILE = "experiment_results.csv"


def listen_for_stats(stop_event, round_times, multicast_count):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Add this line
    sock.bind(("", MULTICAST_PORT_ROUND_TIMES))
    group = socket.inet_aton(MULTICAST_GROUP)
    mreq = group + socket.inet_aton("0.0.0.0")
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.settimeout(1.0)

    # Fireworks socket
    sock_fireworks = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_fireworks.setsockopt(
        socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
    )  # Add this line
    sock_fireworks.bind(("", MULTICAST_PORT_FIREWORKS))
    group_fireworks = socket.inet_aton(MULTICAST_GROUP_FIREWORKS)
    mreq_fireworks = group_fireworks + socket.inet_aton("0.0.0.0")
    sock_fireworks.setsockopt(
        socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq_fireworks
    )
    sock_fireworks.settimeout(1.0)

    while not stop_event.is_set():
        try:
            # Check for round time messages
            ready_to_read, _, _ = select.select([sock, sock_fireworks], [], [], 1.0)
            for ready_sock in ready_to_read:
                data, _ = ready_sock.recvfrom(1024)
                message = data.decode()
                if ready_sock == sock:
                    # Round time message
                    message = json.loads(message)
                    if message.get("type") == "round_time":
                        round_times.append(message["duration"])
                else:
                    # Firework message
                    if "Firework from" in message:
                        multicast_count[0] += 1

        except socket.timeout:
            continue
        except Exception as e:
            print("Error receiving multicast:", e)

    sock.close()
    sock_fireworks.close()


def cleanup_processes(processes):
    for proc in processes:
        try:
            proc.terminate()
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()


def run_single_ring(n, initial_p, k):
    processes = []
    round_times = []
    multicast_count = [0]

    stop_event = threading.Event()
    listener = threading.Thread(
        target=listen_for_stats, args=(stop_event, round_times, multicast_count)
    )
    listener.start()

    try:
        for i in range(n):
            port = BASE_PORT + i
            next_port = BASE_PORT + ((i + 1) % n)
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "process.py",
                    "--id",
                    str(i),
                    "--port",
                    str(port),
                    "--next_port",
                    str(next_port),
                    "--initial_p",
                    str(initial_p),
                    "--k",
                    str(k),
                ]
            )
            processes.append(proc)

        time.sleep(2)  # Let the ring settle

        # Send first token
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        token = {"round": 0, "silent_rounds": 0, "timestamp": time.time()}
        sock.sendto(json.dumps(token).encode(), ("localhost", BASE_PORT))

        # Wait for completion
        start_time = time.time()
        while any(p.poll() is None for p in processes):
            # If the processes take over 60 seconds, we assume an error occured
            if time.time() - start_time > MAX_WAIT_TIME:
                raise TimeoutError("Process ring took too long.")
            time.sleep(1)

        stop_event.set()
        listener.join()

        if round_times:
            return {
                "n": n,
                "rounds": len(round_times),
                "multicasts": multicast_count[0],
                "min_time": min(round_times),
                "max_time": max(round_times),
                "avg_time": mean(round_times),
            }
        else:
            return None

    finally:
        cleanup_processes(processes)
        stop_event.set()
        listener.join()


def run_experiments(max_n=6, initial_p=0.5, k=5, step=4):
    results = []
    for n in range(2, max_n + 1, step):
        print(f"\nRunning experiment with n={n}...")
        try:
            stats = run_single_ring(n, initial_p, k)
            if stats:
                print(f"Success: {stats}")
                results.append(
                    {
                        "n": stats["n"],
                        "rounds": stats["rounds"],
                        "multicasts": stats["multicasts"],
                        "min_time": f"{stats['min_time']:.6f}",
                        "max_time": f"{stats['max_time']:.6f}",
                        "avg_time": f"{stats['avg_time']:.6f}",
                    }
                )
            else:
                print(f"Failed to collect stats for n={n}.")
                break
        except Exception as e:
            print(f"Error at n={n}: {e}")
            break

    print("\nFinal Results:")
    for r in results:
        print(r)

    max_success_n = results[-1]["n"] if results else 1
    print(f"\nMaximum successful n: {max_success_n}")

    # Write results to CSV
    fieldnames = ["n", "rounds", "multicasts", "min_time", "max_time", "avg_time"]
    with open(CSV_FILE, mode="w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "n": result["n"],
                    "rounds": result["rounds"],
                    "multicasts": result["multicasts"],
                    "min_time": result["min_time"],
                    "max_time": result["max_time"],
                    "avg_time": result["avg_time"],
                }
            )


if __name__ == "__main__":
    run_experiments()
