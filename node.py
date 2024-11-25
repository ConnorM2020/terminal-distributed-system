import sys
import re
import json
import socket
import threading
from datetime import datetime
import uuid


# Utility for formatted logging
def log_message(message_type, details):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {message_type}: {details}")


class Transaction:
    def __init__(self, txn_id=None, amount=None, sender=None, receiver=None, **kwargs):
        self.id = txn_id or str(uuid.uuid4())
        self.amount = amount
        self.sender = sender
        self.receiver = receiver
        self.timestamp = datetime.now().isoformat()

    def to_dict(self):
        return {
            "id": self.id,
            "amount": self.amount,
            "sender": self.sender,
            "receiver": self.receiver,
            "timestamp": self.timestamp,
        }


class Node:
    def __init__(self, nickname, address):
        self.node_id = str(uuid.uuid4())
        self.nickname = nickname
        self.address = address
        self.balance = 1000.0
        self.peers = []
        self.transactions = {}
        self.running = True
        self.transaction_counter = 0

        # Validate IP Address
        host, port = self.address.split(":")
        try:
            socket.inet_aton(host)
        except socket.error:
            raise ValueError(f"Invalid IP address: {host}")

        # Create a UDP Socket
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind((host, int(port)))
        log_message("Node Start", f"{self.nickname} listening on {self.address} (UDP)")

    def process_transaction(self, txn):
        if txn.id in self.transactions:
            return False, "Transaction already processed."

        if txn.receiver == self.address:
            self.balance += txn.amount
            self.transactions[txn.id] = txn
            return True, "Transaction received and balance updated."
        return False, "Transaction not for this node."

    def send_transaction(self, receiver_address, amount):
        if self.balance < amount:
            log_message("Error", "Insufficient balance to send transaction.")
            return

        txn_id = f"txn-{self.transaction_counter}"
        self.transaction_counter += 1
        txn = Transaction(
            txn_id=txn_id, amount=amount, sender=self.address, receiver=receiver_address
        )

        self.balance -= amount
        self.transactions[txn.id] = txn

        log_message("Transaction", f"Sending to {receiver_address}: {txn.to_dict()}")
        self.broadcast_transaction(txn)

    def broadcast_transaction(self, txn):
        for peer in self.peers:
            self.send_udp_message("transaction", txn.to_dict(), peer)

    def send_udp_message(self, message_type, data, peer_address):
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}:\d+$", peer_address):
            log_message("Error", f"Invalid peer address: {peer_address}. Format: IP:PORT")
            return

        message = {
            "message_id": str(uuid.uuid4()),
            "type": message_type,
            "data": data,
        }
        try:
            peer_host, peer_port = peer_address.split(":")
            self.udp_socket.sendto(json.dumps(message).encode("utf-8"), (peer_host, int(peer_port)))
            log_message("Message Sent", f"To {peer_address}: {message}")
        except Exception as e:
            log_message("Error", f"Failed to send message to {peer_address}: {e}")

    def handle_udp_message(self, data, addr):
        try:
            message = json.loads(data.decode("utf-8"))
            sender_address = f"{addr[0]}:{addr[1]}"
            message_type = message.get("type")

            log_message("Message Received", f"From {sender_address}: {message_type}")

            if message_type == "transaction":
                txn_data = message.get("data", {})
                txn = Transaction(**txn_data)
                success, msg = self.process_transaction(txn)
                if success:
                    log_message("Transaction Processed", txn.to_dict())
            elif message_type == "ping":
                self.add_peer(sender_address)
                self.send_udp_message("ping_ack", {"data": "Pong"}, sender_address)
            elif message_type == "ping_ack":
                log_message("Ping Acknowledged", f"From {sender_address}")
            elif message_type == "details_request":
                self.send_node_details(sender_address)
            elif message_type == "discovery_request":
                self.handle_discovery_request(sender_address)
            elif message_type == "balance_request":
                self.handle_balance_request(sender_address)
            elif message_type == "balance_response":
                self.handle_balance_response(message.get("data", {}), sender_address)
        except Exception as e:
            log_message("Error", f"Handling message from {addr}: {e}")

    def add_peer(self, peer_address):
        if peer_address not in self.peers and peer_address != self.address:
            self.peers.append(peer_address)
            log_message("Peer Added", f"{peer_address}")

    def send_node_details(self, peer_address):
        details = {
            "nickname": self.nickname,
            "address": self.address,
            "balance": self.balance,
            "peers": self.peers,
        }
        self.send_udp_message("details_response", details, peer_address)

    def handle_discovery_request(self, sender_address):
        self.add_peer(sender_address)
        response = {"peers": self.peers}
        self.send_udp_message("discovery_response", response, sender_address)

    def handle_balance_request(self, sender_address):
        self.send_udp_message("balance_response", {"balance": self.balance}, sender_address)

    def handle_balance_response(self, data, sender_address):
        balance = data.get("balance")
        log_message("Balance Received", f"{sender_address} has balance {balance}")

    def request_discovery(self):
        """Request discovery of other nodes from connected peers."""
        for peer in self.peers:
            self.send_udp_message("discovery_request", {}, peer)

    def synchronize_transactions(self):
        """Synchronize transactions with all connected peers."""
        for peer in self.peers:
            self.send_udp_message("sync_request", {}, peer)

    def join_network(self, peer_address):
        """Join the network by connecting to a peer."""
        log_message("Joining Network", f"Connecting to {peer_address}")
        self.add_peer(peer_address)
        self.request_discovery()

    def listen(self):
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                threading.Thread(target=self.handle_udp_message, args=(data, addr)).start()
            except Exception as e:
                log_message("Error", f"Listening loop: {e}")

    def stop(self):
        self.running = False
        self.udp_socket.close()


def print_menu():
    """Print menu options."""
    print("\n=== Node Menu ===")
    print("1. List Peers")
    print("2. Add Peer")
    print("3. Send Transaction")
    print("4. List Transactions")
    print("5. Send Ping")
    print("6. Get Node Details")
    print("7. Request Discovery")
    print("8. Synchronize Transactions")
    print("9. Join Network")
    print("10. Request Balance")
    print("11. Exit")


def start_node(port, ip="0.0.0.0"):
    nickname = f"Node-{port}"
    address = f"{ip}:{port}"
    node = Node(nickname, address)
    threading.Thread(target=node.listen, daemon=True).start()

    while True:
        print_menu()
        choice = input("Enter your choice: ")

        if choice == "1":
            print("\nConnected peers:")
            for peer in node.peers:
                print(f"- {peer}")
        elif choice == "2":
            peer = input("Enter peer address (IP:PORT): ")
            node.add_peer(peer)
        elif choice == "3":
            receiver = input("Enter receiver address: ")
            amount = float(input("Enter amount: "))
            node.send_transaction(receiver, amount)
        elif choice == "4":
            for txn in node.transactions.values():
                print(f"- {txn.to_dict()}")
        elif choice == "5":
            peer = input("Enter peer address to ping: ")
            node.send_udp_message("ping", {"data": "Hello"}, peer)
        elif choice == "6":
            peer = input("Enter peer address to request details: ")
            node.send_udp_message("details_request", {}, peer)
        elif choice == "7":
            node.request_discovery()
        elif choice == "8":
            node.synchronize_transactions()
        elif choice == "9":
            peer = input("Enter peer address to join the network: ")
            node.join_network(peer)
        elif choice == "10":
            peer = input("Enter peer address to request balance: ")
            node.send_udp_message("balance_request", {}, peer)
        elif choice == "11":
            node.stop()
            sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python node.py <port> [<ip>]")
        sys.exit(1)

    port = int(sys.argv[1])
    ip = sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0"
    start_node(port, ip)
