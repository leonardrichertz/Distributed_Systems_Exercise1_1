import subprocess
import time
import socket
import json
import threading
from statistics import mean
import sys
import csv

MULTICAST_GROUP = '224.1.1.1'
MULTICAST_PORT_ROUND_TIMES = 5008
BASE_PORT = 6000
MAX_WAIT_TIME = 60 
CSV_FILE = 'experiment_results.csv'

def listen_for_stats(stop_event, round_times, multicast_count):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', MULTICAST_PORT_ROUND_TIMES))
    group = socket.inet_aton(MULTICAST_GROUP)   
    mreq = group + socket.inet_aton('0.0.0.0')
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    sock.settimeout(1.0)
    while not stop_event.is_set():
        try:
            data, _ = sock.recvfrom(1024)
            message = json.loads(data.decode())
            if message.get("type") == "round_time":
                round_times.append(message["duration"])
                multicast_count[0] += 1
        except socket.timeout:
            continue
        except Exception as e:
            print("Error receiving multicast:", e)

    sock.close()

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
    listener = threading.Thread(target=listen_for_stats, args=(stop_event, round_times, multicast_count))
    listener.start()

    try:
        for i in range(n):
            port = BASE_PORT + i
            next_port = BASE_PORT + ((i + 1) % n)
            proc = subprocess.Popen([
                sys.executable, 'process.py',
                '--id', str(i),
                '--port', str(port),
                '--next_port', str(next_port),
                '--initial_p', str(initial_p),
                '--k', str(k)
            ])
            processes.append(proc)

        time.sleep(2)  # Let the ring settle

        # Send first token
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        token = {'round': 0, 'silent_rounds': 0, 'timestamp': time.time()}
        sock.sendto(json.dumps(token).encode(), ('localhost', BASE_PORT))

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
                'n': n,
                'rounds': len(round_times),
                'multicasts': multicast_count[0],
                'min_time': min(round_times),
                'max_time': max(round_times),
                'avg_time': mean(round_times)
            }
        else:
            return None

    finally:
        cleanup_processes(processes)
        stop_event.set()
        listener.join()

def run_experiments(max_n=100, initial_p=0.5, k=5):
    results = []
    for n in range(2, max_n + 1):
        print(f"\nRunning experiment with n={n}...")
        try:
            stats = run_single_ring(n, initial_p, k)
            if stats:
                print(f"Success: {stats}")
                results.append({
                    'n': stats['n'],
                    'rounds': stats['rounds'],
                    'multicasts': stats['multicasts'],
                    'min_time': f"{stats['min_time']:.6f}",
                    'max_time': f"{stats['max_time']:.6f}",
                    'avg_time': f"{stats['avg_time']:.6f}"
                })
            else:
                print(f"Failed to collect stats for n={n}.")
                break
        except Exception as e:
            print(f"Error at n={n}: {e}")
            break

    print("\nFinal Results:")
    for r in results:
        print(r)

    max_success_n = results[-1]['n'] if results else 1
    print(f"\nMaximum successful n: {max_success_n}")

    # Write results to CSV
    fieldnames = ['n', 'rounds', 'multicasts', 'min_time', 'max_time', 'avg_time']
    with open(CSV_FILE, mode='w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

if __name__ == "__main__":
    run_experiments()
