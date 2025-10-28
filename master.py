import os
import subprocess
import sys


def main():
    # Master node just initiates alpha service inside its own container/network
    # In docker-compose, alpha runs as a separate service; here we just print guidance
    print("[Master] Triggering Alpha Service...")
    try:
        # If alpha is colocated, we could call it directly.
        # In compose, alpha runs independently; master could signal via HTTP/RPC in future.
        # For now, just exec alpha_service.py if present.
        if os.path.exists("alpha_service.py"):
            proc = subprocess.run([sys.executable, "alpha_service.py"], check=False)
            sys.exit(proc.returncode)
        else:
            print("[Master] alpha_service.py not found in this container. Ensure alpha service runs as its own compose service.")
            sys.exit(0)
    except Exception as e:
        print(f"[Master] Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()


