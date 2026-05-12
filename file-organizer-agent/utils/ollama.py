"""
utils/ollama.py — ensures Ollama server and model are ready before
the agent starts. Called once at startup from main.py.
"""

import subprocess
import time

import httpx
import ollama
from rich.console import Console

from config import OLLAMA_MODEL, OLLAMA_URL

console = Console()

_server_process: subprocess.Popen | None = None


def ensure_ollama_ready(model: str=OLLAMA_MODEL, timeout: int=30) -> None:
    """
    Ensure the Ollama server is running and the required model is available.

    Steps:
      1. Check if the Ollama server responds on localhost.
      2. If not → start `ollama serve` as a background process and wait.
      3. Check if the model is pulled locally.
      4. If not → pull it (blocking, shows progress).
    """
    _ensure_server_running(timeout)
    _ensure_model_available(model)


def _ensure_server_running(timeout: int) -> None:
    global _server_process
    """Start `ollama serve` if the server is not reachable."""
    url = f"{OLLAMA_URL}/api/tags"

    try:
        httpx.get(url, timeout=2)
        console.print("  [dim]Ollama server already running.[/dim]")
        return
    except (httpx.ConnectError, httpx.ConnectTimeout):
        pass

    console.print("  [yellow]Ollama server not running — starting it...[/yellow]")
    _server_process = subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            httpx.get(url, timeout=2)
            console.print("  [green]✓ Ollama server started.[/green]")
            return
        except (httpx.ConnectError, httpx.ConnectTimeout):
            time.sleep(1)

    raise RuntimeError(
        f"Ollama server did not respond within {timeout}s.\n"
        "Try running `ollama serve` manually and check for errors."
    )


def _ensure_model_available(model: str) -> None:
    """Pull the model if it is not already present locally."""
    client = ollama.Client(host=OLLAMA_URL)

    # client.list() returns a ListResponse object in newer ollama versions.
    # Each entry is a Model object with a .model attribute, not a dict.
    response = client.list()
    models = getattr(response, "models", None) or response.get("models", [])

    available = []
    for m in models:
        # new API: Model object  →  m.model
        # old API: plain dict    →  m["name"]
        name = getattr(m, "model", None) or m.get("name", "") or m.get("model", "")
        available.append(name)

    is_present = any(m.startswith(model) for m in available)

    if is_present:
        console.print(f"  [dim]Model '{model}' already available.[/dim]")
        return

    console.print(
        f"  [yellow]Model '{model}' not found locally — pulling...[/yellow]\n"
        "  This may take a few minutes on first run."
    )
    for progress in client.pull(model, stream=True):
        status = progress.get("status", "")
        total = progress.get("total", 0)
        done = progress.get("completed", 0)
        if total:
            console.print(f"  [dim]{status}: {done / total * 100:.1f}%[/dim]", end="\r")
        else:
            console.print(f"  [dim]{status}[/dim]", end="\r")

    console.print(f"\n  [green]✓ Model '{model}' ready.[/green]")

    
def shutdown_ollama(model: str=OLLAMA_MODEL) -> None:
    # 1. Unload the model via the REST API directly (bypasses client quirks)
    try:
        httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "keep_alive": 0},
            timeout=10,
        )
        console.print(f"  [dim]Model '{model}' unloaded.[/dim]")
    except (httpx.ConnectError, httpx.ConnectTimeout):
        console.print("  [yellow]Server already stopped — skipping model unload.[/yellow]")
    except Exception as e:
        console.print(f"  [yellow]Could not unload model: {e}[/yellow]")

    # 2. Stop the server — only if this session started it (unchanged)
    if _server_process is not None:
        _server_process.terminate()
        try:
            _server_process.wait(timeout=5)
            console.print("  [dim]Ollama server stopped.[/dim]")
        except subprocess.TimeoutExpired:
            _server_process.kill()
            console.print("  [yellow]Ollama server force-killed.[/yellow]")
    else:
        console.print("  [dim]Ollama server was pre-existing — left running.[/dim]")
