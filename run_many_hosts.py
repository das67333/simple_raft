import subprocess
import signal
import sys
import threading


# Запуск процесса и перенаправления вывода с меткой номера сервера
def run_server(idx: str, ports: list[str]):
    return subprocess.Popen(
        ["python", "main.py", idx, *ports],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

# Чтение и вывод stdout/stderr с меткой


def stream_output(process, server_id):
    def read_stream(stream):
        for line in iter(stream.readline, ''):
            print(f"[Server {server_id}] {line}", end='')
        stream.close()

    stdout_thread = threading.Thread(
        target=read_stream, args=(process.stdout,))
    stderr_thread = threading.Thread(
        target=read_stream, args=(process.stderr,))

    stdout_thread.start()
    stderr_thread.start()

    return stdout_thread, stderr_thread


# Обработчик сигнала для остановки всех процессов
def handle_interrupt(signum, frame):
    print("\nStopping all servers...")
    sys.stderr.close()
    sys.stdout.close()
    for process in processes:
        process.terminate()
    sys.exit(0)


if __name__ == "__main__":
    start_port, n = 50020, 3
    ports = list(map(str, range(start_port, start_port + n)))

    processes = []
    threads = []

    # Перехват сигнала прерывания
    signal.signal(signal.SIGINT, handle_interrupt)

    try:
        for i in range(n):
            process = run_server(str(i), ports)
            processes.append(process)
            threads.extend(stream_output(process, i))

    except KeyboardInterrupt:
        handle_interrupt(None, None)
