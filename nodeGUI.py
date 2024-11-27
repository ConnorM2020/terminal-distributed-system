import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog
import threading
import time
import random
from node import Node, Transaction

class NodeGUI:
    def __init__(self, master, port, ip="0.0.0.0"):
        self.master = master
        self.node_name = f"Node-{port}"
        self.master.title(f"{self.node_name} GUI")
        self.node = None
        self.robot_running = False  # Flag for the robot
        self.setup_gui()
        self.node = Node(self.node_name, f"{ip}:{port}", log_callback=self.log_message)
        threading.Thread(target=self.node.listen, daemon=True).start()

    def setup_gui(self):
        # Display Node Name
        tk.Label(self.master, text=f"Node: {self.node_name}", font=("Arial", 16)).pack(pady=10)

        # Frame for peer management
        peer_frame = tk.LabelFrame(self.master, text="Peer Management", padx=5, pady=5)
        peer_frame.pack(fill="x", padx=10, pady=5)

        tk.Button(peer_frame, text="List Peers", command=self.list_peers).pack(side="left", padx=5, pady=5)
        tk.Button(peer_frame, text="Add Peer", command=self.add_peer).pack(side="left", padx=5, pady=5)
        tk.Button(peer_frame, text="Request Discovery", command=self.request_discovery).pack(side="left", padx=5, pady=5)
        tk.Button(peer_frame, text="Join Network", command=self.join_network).pack(side="left", padx=5, pady=5)

        # Frame for transaction management
        txn_frame = tk.LabelFrame(self.master, text="Transactions", padx=5, pady=5)
        txn_frame.pack(fill="x", padx=10, pady=5)

        tk.Button(txn_frame, text="Send Transaction", command=self.send_transaction).pack(side="left", padx=5, pady=5)
        tk.Button(txn_frame, text="List Transactions", command=self.list_transactions).pack(side="left", padx=5, pady=5)
        tk.Button(txn_frame, text="Synchronize Transactions", command=self.synchronize_transactions).pack(side="left", padx=5, pady=5)

        # Frame for communication
        comm_frame = tk.LabelFrame(self.master, text="Communication", padx=5, pady=5)
        comm_frame.pack(fill="x", padx=10, pady=5)

        tk.Button(comm_frame, text="Send Ping", command=self.send_ping).pack(side="left", padx=5, pady=5)
        tk.Button(comm_frame, text="Get Node Details", command=self.get_node_details).pack(side="left", padx=5, pady=5)
        tk.Button(comm_frame, text="Request Balance", command=self.request_balance).pack(side="left", padx=5, pady=5)

        # Robot automation
        robot_frame = tk.LabelFrame(self.master, text="Robot Automation", padx=5, pady=5)
        robot_frame.pack(fill="x", padx=10, pady=5)

        tk.Button(robot_frame, text="Start Robot", command=self.start_robot).pack(side="left", padx=5, pady=5)
        tk.Button(robot_frame, text="Stop Robot", command=self.stop_robot).pack(side="left", padx=5, pady=5)

        # Log area
        log_frame = tk.LabelFrame(self.master, text="Logs", padx=5, pady=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.log_display = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=15)
        self.log_display.pack(fill="both", expand=True)

    def log_message(self, message):
        """Display messages in the log area."""
        self.log_display.insert(tk.END, f"{message}\n")
        self.log_display.see(tk.END)

    def list_peers(self):
        peers = "\n".join(self.node.peers) if self.node.peers else "No peers connected."
        self.log_message(f"Peers:\n{peers}")

    def add_peer(self):
        peer = simpledialog.askstring("Add Peer", "Enter peer address (IP:PORT):")
        if peer:
            self.node.add_peer(peer)
            self.log_message(f"Added peer: {peer}")

    def request_discovery(self):
        self.node.request_discovery()
        self.log_message("Requested discovery from peers.")

    def join_network(self):
        peer = simpledialog.askstring("Join Network", "Enter peer address (IP:PORT):")
        if peer:
            self.node.join_network(peer)
            self.log_message(f"Joined network via {peer}")

    def send_transaction(self):
        receiver = simpledialog.askstring("Send Transaction", "Enter receiver address:")
        if not receiver:
            return

        try:
            amount = float(simpledialog.askstring("Send Transaction", "Enter amount:"))
            self.node.send_transaction(receiver, amount)
            self.log_message(f"Sent transaction to {receiver} with amount {amount}")
        except ValueError:
            self.log_message("Invalid amount entered.")

    def list_transactions(self):
        transactions = "\n".join([str(txn.to_dict()) for txn in self.node.transactions.values()]) or "No transactions found."
        self.log_message(f"Transactions:\n{transactions}")

    def synchronize_transactions(self):
        self.node.synchronize_transactions()
        self.log_message("Synchronized transactions with peers.")
        
    def toggle_failure_simulation(self):
        self.node.failure_simulation = not self.node.failure_simulation
        status = "enabled" if self.node.failure_simulation else "disabled"
        self.log_message(f"Failure simulation {status}.")

    def send_ping(self):
        peer = simpledialog.askstring("Send Ping", "Enter peer address (IP:PORT):")
        if peer:
            self.node.send_udp_message("ping", {"data": "Ping"}, peer)
            self.log_message(f"Ping sent to {peer}")

    def get_node_details(self):
        details = {
            "Node Name": self.node.nickname,
            "Address": self.node.address,
            "Balance": self.node.balance,
            "Peers": "\n".join(self.node.peers) or "No peers connected.",
        }
        details_message = "\n".join([f"{key}: {value}" for key, value in details.items()])
        messagebox.showinfo("Node Details", details_message)

    def request_balance(self):
        peer = simpledialog.askstring("Request Balance", "Enter peer address (IP:PORT):")
        if peer:
            self.node.send_udp_message("balance_request", {}, peer)
            self.log_message(f"Requested balance from {peer}")

    def start_robot(self):
        """Start automated robot tasks."""
        self.robot_running = True
        threading.Thread(target=self.robot_task, daemon=True).start()
        self.log_message("Robot started.")

    def stop_robot(self):
        """Stop automated robot tasks."""
        self.robot_running = False
        self.log_message("Robot stopped.")

    def robot_task(self):
        """Perform automated tasks in a loop."""
        while self.robot_running:
            if not self.node.peers:
                time.sleep(1)
                continue
            # Randomly select actions
            action = random.choice(["transaction", "ping", "balance"])
            peer = random.choice(self.node.peers)
            if action == "transaction":
                amount = random.uniform(1, 50)
                self.node.send_transaction(peer, amount)
                self.log_message(f"Robot: Sent transaction to {peer} with amount {amount:.2f}")
            elif action == "ping":
                self.node.send_udp_message("ping", {"data": "Ping from robot"}, peer)
                self.log_message(f"Robot: Pinged {peer}")
            elif action == "balance":
                self.node.send_udp_message("balance_request", {}, peer)
                self.log_message(f"Robot: Requested balance from {peer}")
            time.sleep(random.randint(2, 5))  # Delay between actions


def start_gui(port, ip="0.0.0.0"):
    root = tk.Tk()
    app = NodeGUI(root, port, ip)
    root.protocol("WM_DELETE_WINDOW", lambda: app.node.stop() or root.destroy())
    root.mainloop()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python nodeGUI.py <port> [<ip>]")
        sys.exit(1)

    port = int(sys.argv[1])
    ip = sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0"
    start_gui(port, ip)
