import sys
import re
import json
import socket
import threading
from datetime import datetime
import uuid
import time


# Transaction class to handle individual transactions
class Transaction:
    def __init__(self, txn_id=None, amount=None, sender=None, receiver=None, **kwargs):
        self.id = txn_id or str(uuid.uuid4())  # Generate a UUID if no ID is provided
        self.amount = amount
        self.sender = sender
        self.receiver = receiver
        self.timestamp = datetime.now().isoformat()

    def to_dict(self):
        """Convert the transaction object to a dictionary."""
        return {
            "id": self.id,
            "amount": self.amount,
            "sender": self.sender,
            "receiver": self.receiver,
            "timestamp": self.timestamp,
        }


# Node class to represent a node in the network
class Node:
    def __init__(self, nickname, address):
        self.node_id = str(uuid.uuid4())  # Unique ID for the node
        self.nickname = nickname
        self.address = address
        self.balance = 1000.0  # Initial balance for the node
        self.peers = []  # List of connected peer addresses
        self.transactions = {}  # Dictionary of processed transactions
        self.running = True  # Flag to keep the node running
        self.transaction_counter = 0  # Counter for transaction IDs

        # Validate the IP address
        host, port = self.address.split(":")
        try:
            socket.inet_aton(host)  # Check if the IP address is valid
        except socket.error:
            raise ValueError(f"Invalid IP address: {host}")

        # Create a single UDP socket for both sending and receiving
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind((host, int(port)))  # Bind to the specified IP and port
        print(f"Node {self.nickname} listening on {self.address} (UDP)")

    def process_transaction(self, txn):
        """Process a received transaction."""
        if txn.id in self.transactions:
            return False, "Transaction already processed."

        if txn.receiver == self.address:
            # Update receiver balance
            self.balance += txn.amount
            self.transactions[txn.id] = txn
            return True, "Transaction received and balance updated."

        return False, "Transaction not for this node."

    def send_transaction(self, receiver_address, amount):
        """Create and broadcast a transaction."""
        if self.balance < amount:
            print("\nInsufficient balance to send transaction.")
            return

        txn_id = f"txn-{self.transaction_counter}"
        self.transaction_counter += 1

        # Create the transaction
        txn = Transaction(
            txn_id=txn_id, amount=amount, sender=self.address, receiver=receiver_address
        )

        # Deduct balance from the sender
        self.balance -= amount
        self.transactions[txn.id] = txn

        # Log transaction details
        print(f"\nSending transaction to {receiver_address}:")
        print(json.dumps(txn.to_dict(), indent=4))

        # Broadcast the transaction to all peers
        self.broadcast_transaction(txn)

    def broadcast_transaction(self, txn):
        """Broadcast a transaction to all peers."""
        for peer in self.peers:
            self.send_udp_message("transaction", txn.to_dict(), peer)

    def send_udp_message(self, message_type, data, peer_address):
        """Send a UDP message with a unique message ID."""
        # Validate the peer address format
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}:\d+$", peer_address):
            print(f"\nInvalid peer address format: {peer_address}. Expected format is IP:PORT (e.g., 192.168.1.100:5001).")
            return

        message = {
            "message_id": str(uuid.uuid4()),  # Unique ID for the message
            "type": message_type,
            "data": data,
        }
        try:
            peer_host, peer_port = peer_address.split(":")
            self.udp_socket.sendto(json.dumps(message).encode("utf-8"), (peer_host, int(peer_port)))
            print(f"Message sent to {peer_address}: {message}")
        except (socket.gaierror, ConnectionResetError) as e:
            print(f"Error sending message to {peer_address}: {e}")
            if peer_address in self.peers:
                self.peers.remove(peer_address)


    def request_balance(self, peer_address):
        """Request the balance from a peer."""
        self.send_udp_message("balance_request", {}, peer_address)

    def handle_balance_request(self, sender_address):
        """Handle a balance request and send the balance to the requesting peer."""
        self.send_udp_message("balance_response", {"balance": self.balance}, sender_address)

    def handle_balance_response(self, data, sender_address):
        """Handle a balance response."""
        balance = data.get("balance")
        print(f"\nBalance of {sender_address}: {balance}")

    def synchronize_indexes(self):
        """Request transaction indexes from all peers and synchronize."""
        for peer in self.peers:
            self.send_udp_message("sync_request", {}, peer)

    def handle_sync_request(self, sender_address):
        """Respond to a synchronization request with local transactions."""
        response = {"transactions": [txn.to_dict() for txn in self.transactions.values()]}
        self.send_udp_message("sync_response", response, sender_address)

    def handle_sync_response(self, data, sender_address):
        """Merge transactions received from a sync response."""
        new_transactions = data.get("transactions", [])
        for txn_data in new_transactions:
            txn = Transaction(**txn_data)
            if txn.id not in self.transactions:
                self.transactions[txn.id] = txn
                print(f"Transaction {txn.id} synchronized from {sender_address}.")

    def join_network(self, peer_address):
        """Join the network via a known peer."""
        self.add_peer(peer_address)
        self.request_discovery()
        self.synchronize_indexes()

    def listen(self):
        """Start listening for UDP messages using the node's existing socket."""
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                threading.Thread(target=self.handle_udp_message, args=(data, addr)).start()
            except ConnectionResetError:
                print("\nConnection reset by remote host. Ignoring and continuing to listen.")
            except Exception as e:
                print(f"\nError in listening loop: {e}")

    def handle_udp_message(self, data, addr):
        """Handle incoming UDP messages."""
        try:
            # Decode the received message
            message = json.loads(data.decode("utf-8"))
            sender_address = f"{addr[0]}:{addr[1]}"
            message_type = message.get("type")

            print(f"\nReceived message of type '{message_type}' from {sender_address}")

            # Handle message types
            if message_type == "transaction":
                txn_data = message.get("data", {})
                txn = Transaction(**txn_data)
                success, msg = self.process_transaction(txn)
                if success:
                    print(f"\nTransaction processed successfully:")
                    print(f"- {txn.to_dict()}")
                    # Broadcast transaction to others
                    self.broadcast_transaction(txn)
            elif message_type == "sync_request":
                self.handle_sync_request(sender_address)
            elif message_type == "sync_response":
                self.handle_sync_response(message.get("data", {}), sender_address)
            elif message_type == "balance_request":
                self.handle_balance_request(sender_address)
            elif message_type == "balance_response":
                self.handle_balance_response(message.get("data", {}), sender_address)
            elif message_type == "ping":
                self.add_peer(sender_address)
            elif message_type == "details_request":
                self.send_node_details(sender_address)
            elif message_type == "discovery_request":
                self.handle_discovery_request(sender_address)
            elif message_type == "discovery_response":
                self.handle_discovery_response(message.get("data", {}), sender_address)
        except json.JSONDecodeError:
            print(f"\nError decoding message from {addr}: {data}")
        except Exception as e:
            print(f"\nUnexpected error handling message from {addr}: {e}")

    def add_peer(self, peer_address):
        """Add a peer to the peers list if not already present."""
        if peer_address not in self.peers and peer_address != self.address:
            self.peers.append(peer_address)
            print(f"\nNode {peer_address} added to peers list.")

    def send_node_details(self, peer_address):
        """Send this node's details to a requesting peer."""
        details = {
            "nickname": self.nickname,
            "address": self.address,
            "balance": self.balance,
            "peers": self.peers,
        }
        self.send_udp_message("details_response", details, peer_address)

    def request_discovery(self):
        """Request discovery of other nodes from connected peers."""
        for peer in self.peers:
            self.send_udp_message("discovery_request", {}, peer)

    def handle_discovery_request(self, sender_address):
        """Handle a discovery request and send a response with known peers."""
        self.add_peer(sender_address)
        response = {"peers": self.peers}
        self.send_udp_message("discovery_response", response, sender_address)

    def handle_discovery_response(self, data, sender_address):
        """Handle a discovery response and update the peer list."""
        new_peers = data.get("peers", [])
        for peer in new_peers:
            if peer not in self.peers and peer != self.address:
                self.add_peer(peer)

    def stop(self):
        """Stop the node."""
        self.running = False
        self.udp_socket.close()


def print_menu():
    """Print the Node menu."""
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
    """Start the node."""
    nickname = f"Node-{port}"
    address = f"{ip}:{port}"
    node = Node(nickname, address)
    threading.Thread(target=node.listen, daemon=True).start()

    while True:
        print_menu()
        choice = input("Enter your choice: ")

        if choice == "1":
            if not node.peers:
                print("\nNo peers connected.")
            else:
                print("\nConnected peers:")
                for peer in node.peers:
                    print(f"- {peer}")
        elif choice == "2":
            peer = input("Enter peer address (e.g., 192.168.1.100:5001): ")
            node.add_peer(peer)
        elif choice == "3":
            receiver = input("Enter receiver address: ")
            amount = float(input("Enter amount: "))
            node.send_transaction(receiver, amount)
        elif choice == "4":
            if not node.transactions:
                print("\nNo transactions available.")
            else:
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
            node.synchronize_indexes()
        elif choice == "9":
            peer = input("Enter peer address to join the network: ")
            node.join_network(peer)
        elif choice == "10":
            peer = input("Enter peer address to request balance: ")
            node.request_balance(peer)
        elif choice == "11":
            node.stop()
            sys.exit(0)
        else:
            print("Invalid choice. Try again.")
            
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python node.py <port> [<ip>]")
        sys.exit(1)

    port = int(sys.argv[1])
    ip = sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0"
    start_node(port, ip)
