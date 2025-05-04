import socket
import argparse
import json
import random
import time
import struct
import threading

MULTICAST_GROUP = '224.0.0.1'
MULTICAST_PORT = 5007
BUFFER_SIZE = 1024

def send_token(next_host, next_port, token):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(json.dumps(token).encode(), (next_host, next_port))

def multicast_firework(process_id, round_number):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    message = f"Firework from {process_id} in round {round_number}"
    sock.sendto(message.encode(), (MULTICAST_GROUP, MULTICAST_PORT))

def listen_multicast():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', MULTICAST_PORT))
    mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    def receive():
        while True:
            data, _ = sock.recvfrom(BUFFER_SIZE)
            print("[Multicast] Received:", data.decode())
    
    threading.Thread(target=receive, daemon=True).start()

def main(args):
    try:
        listen_multicast()
        probability = args.initial_p
        rounds_without_firework = 0
        total_rounds = 0

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('localhost', args.port))

        print(f"[Process {args.id}] Started on port {args.port}, next = {args.next_port}")

        while True:
            data, _ = sock.recvfrom(BUFFER_SIZE)
            token = json.loads(data.decode())
            total_rounds += 1
            print(f"[Process {args.id}] Received token in round {token['round']}")

            if random.random() < probability:
                print(f"[Process {args.id}] FIREWORK!")
                multicast_firework(args.id, token["round"])
                rounds_without_firework = 0
            else:
                rounds_without_firework += 1

            probability /= 2
            token['round'] += 1
            token['silent_rounds'] = token.get('silent_rounds', 0) + 1

            if token['silent_rounds'] >= args.k:
                print(f"[Process {args.id}] Terminating after {token['round']} rounds")
                break

            time.sleep(0.1)
            send_token('localhost', args.next_port, token)
            
    finally:
        sock.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', type=int, required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--next_port', type=int, required=True)
    parser.add_argument('--initial_p', type=float, default=0.5)
    parser.add_argument('--k', type=int, default=5)
    main(parser.parse_args())
