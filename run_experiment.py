import subprocess
import time
import argparse
import sys

BASE_PORT = 6000


def cleanup_processes(processes): 
    for proc in processes:
        try:
            proc.terminate()
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
    print("All processes cleaned up.")


def run_ring(n, initial_p, k):
    processes = []
    try:
        for i in range(n):
            port = BASE_PORT + i
            next_port = BASE_PORT + ((i + 1) % n)

            proc = subprocess.Popen([
                'python', 'process.py',
                '--id', str(i),
                '--port', str(port),
                '--next_port', str(next_port),
                '--initial_p', str(initial_p),
                '--k', str(k)
            ])
            processes.append(proc)

        time.sleep(1)  # Let the ring settle

    # Start the first token
        import socket, json
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        token = {'round': 0, 'silent_rounds': 0}
        sock.sendto(json.dumps(token).encode(), ('localhost', BASE_PORT))

        for proc in processes:
            proc.wait()

    except KeyboardInterrupt:
        print("Interrupted by user, cleaning up processes...")
        cleanup_processes(processes)
        sys.exit(0)
    except Exception as e:
        print(f"An error occurred: {e}")
        cleanup_processes(processes)
        sys.exit(1)
    finally:
        cleanup_processes(processes)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--n', type=int, default=4)
    parser.add_argument('--initial_p', type=float, default=0.5)
    parser.add_argument('--k', type=int, default=5)
    args = parser.parse_args()

    run_ring(args.n, args.initial_p, args.k)
