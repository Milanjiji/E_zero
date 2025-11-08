# run_commands.py
import re
import subprocess
import shlex

# ANSI colors
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def extract_commands(paragraph: str):
    """
    Extract all commands inside <cmd>...</cmd> tags.
    Returns a list of command strings.
    """
    return re.findall(r"<cmd>(.*?)</cmd>", paragraph, flags=re.DOTALL)


def run_commands(commands: list):
    """
    Execute commands one-by-one in the user's shell.
    Prints output live.
    """
    for cmd in commands:
        clean_cmd = cmd.strip()  

        print(f"\n{YELLOW}→ Running:{RESET} {GREEN}{clean_cmd}{RESET}")

        try:
            # Run command and stream output
            process = subprocess.Popen(
                shlex.split(clean_cmd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Forward stdout
            for line in process.stdout:
                print(line, end="")

            # Forward stderr
            for line in process.stderr:
                print(line, end="")

            process.wait()

            if process.returncode == 0:
                print(f"{GREEN}✓ Success{RESET}")
            else:
                print(f"{YELLOW}⚠ Command exited with code {process.returncode}{RESET}")

        except Exception as e:
            print(f"{YELLOW}❌ Error running command: {e}{RESET}")


def execute_microtask_output(paragraph: str):
    """
    High-level function:
    - Extract commands from a microtask response
    - Run them in order (if any exist)
    """
    commands = extract_commands(paragraph)
    if not commands:
        print("\n(No commands found — this microtask only describes an action.)\n")
        return

    run_commands(commands)
