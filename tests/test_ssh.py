import json
import os
import pwd
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner
import urwid

from job import cli, container, monitor, profile_editor, workbench


class SSHConfigTests(unittest.TestCase):
    def test_profile_requires_image_and_persists_opt_in(self):
        editor = profile_editor.ProfileEditor({"name": "default"}, ["batch"])
        editor.container_ssh.set_state(True)
        with tempfile.TemporaryDirectory() as directory, patch(
            "job.places.profile_folder", return_value=directory
        ):
            editor.save(force=True)
            self.assertIn("image is required", editor.container_error.text)
            self.assertEqual(list(Path(directory).iterdir()), [])
            editor.image.set_edit_text("image.sif")
            self.assertIn('--bind "$HOME:$HOME"', editor.container_command.text)
            with self.assertRaises(urwid.ExitMainLoop):
                editor.save(force=True)
            profile = json.loads(Path(directory, "default.json").read_text())
        self.assertTrue(profile["container"]["ssh"])
        self.assertTrue(profile_editor.ProfileEditor(profile, ["batch"]).container_ssh.get_state())

    def test_ssh_config_for_ready_job(self):
        ssh_info = {
            "port": 23456,
            "host_key_alias": "pbs-workbench-" + "a" * 43,
            "fingerprint": "SHA256:" + "A" * 43,
        }
        with patch("job.workbench.workbench_current", return_value=["/tmp/00"]), patch(
            "job.workbench.get_job_id", return_value="123.server"
        ), patch("job.pbsqueue.info", return_value={"state": "R", "hostname": "node-01"}), patch(
            "job.workbench.running_container_ssh", return_value=ssh_info
        ), patch.dict(os.environ, {"USER": "alice"}):
            result = CliRunner().invoke(cli.app, ["ssh-config"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Host pbs-workbench\n", result.output)
        self.assertIn("Port 23456\n", result.output)
        self.assertIn("ProxyCommand ssh -W %h:%p alice@node-01\n", result.output)
        self.assertIn(ssh_info["fingerprint"], result.output)
        if shutil.which("ssh"):
            with tempfile.TemporaryDirectory() as directory:
                config = Path(directory, "config")
                config.write_text(result.output)
                parsed = subprocess.run(
                    ["ssh", "-G", "-F", str(config), "pbs-workbench"],
                    text=True, capture_output=True, check=True,
                )
            self.assertIn("hostname 127.0.0.1\n", parsed.stdout)
            self.assertIn("port 23456\n", parsed.stdout)
            self.assertIn("proxycommand ssh -W %h:%p alice@node-01\n", parsed.stdout)

    def test_ssh_config_is_unavailable_without_endpoint(self):
        with patch("job.workbench.workbench_current", return_value=["/tmp/00"]), patch(
            "job.workbench.get_job_id", return_value="123.server"
        ), patch("job.pbsqueue.info", return_value={"state": "R", "hostname": "node-01"}), patch(
            "job.workbench.running_container_ssh", return_value=None
        ):
            result = CliRunner().invoke(cli.app, ["ssh-config"])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("not ready or is not enabled", result.output)

    def test_endpoint_metadata_validation_and_monitor(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = str(Path(directory, "workbenches", "00"))
            job_id = "123.server"
            name = container.instance_name(job_id)
            folder = Path(workbench.container_ready_dir(marker))
            folder.mkdir(parents=True)
            (folder / name).write_text(job_id + "\n")
            endpoint = folder / (name + ".ssh.json")
            data = {
                "job_id": job_id, "port": 23456,
                "fingerprint": "SHA256:" + "A" * 43,
                "host_key_alias": "pbs-workbench-" + "a" * 43,
            }
            endpoint.write_text(json.dumps(data))
            self.assertEqual(workbench.running_container_ssh(marker, job_id), data)
            data["port"] = 65536
            endpoint.write_text(json.dumps(data))
            self.assertIsNone(workbench.running_container_ssh(marker, job_id))
            endpoint.write_text("invalid json")
            self.assertIsNone(workbench.running_container_ssh(marker, job_id))

        info = {
            "used": {"walltime": 60, "memory": 1024**3, "cpu": 0},
            "requested": {"walltime": 3600, "memory": 8 * 1024**3},
            "job_id": "123.server", "profile": "test", "state": "R",
            "hostname": "node-01", "comment": "", "su": None,
        }
        with patch.dict(os.environ, {"USER": "alice"}):
            canvas = b"\n".join(monitor.build_ui(info, "instance", {"port": 23456}).render((150, 40)).text)
            userns_canvas = b"\n".join(
                monitor.build_ui(info, "instance", {"userns": True}).render((150, 40)).text
            )
        self.assertIn(b"job ssh-config", canvas)
        self.assertIn(b"apptainer shell --userns instance://instance", userns_canvas)


@unittest.skipUnless(
    os.getuid() != 0 and Path("/usr/sbin/sshd").exists() and shutil.which("ssh")
    and shutil.which("ssh-keygen") and Path("/run/sshd").is_dir(),
    "requires unprivileged user and local OpenSSH server",
)
class SSHIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("PBS_WORKBENCH_TEST_IMAGE") and shutil.which("apptainer"),
                         "requires PBS_WORKBENCH_TEST_IMAGE and Apptainer")
    def test_real_apptainer_container_ssh(self):
        for flags in ("", "--userns"):
            with self.subTest(flags=flags):
                self._run_real_apptainer_container_ssh(flags)

    def _run_real_apptainer_container_ssh(self, flags):
        image = os.environ["PBS_WORKBENCH_TEST_IMAGE"]
        data_dir = Path(workbench.__file__).parent / "data"
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            resources = root / "resources"
            resources.mkdir()
            (resources / "idle.sh").write_text(
                (data_dir / "idle.sh").read_text().replace("sleep 30", "sleep 1")
            )
            (resources / "sshd.py").write_text((data_dir / "sshd.py").read_text())
            keys = root / ".ssh"
            keys.mkdir(mode=0o700)
            key = root / "client"
            subprocess.run(
                ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True
            )
            (keys / "authorized_keys").write_text(key.with_suffix(".pub").read_text())
            (keys / "authorized_keys").chmod(0o600)
            profile = root / "profile.json"
            profile.write_text(json.dumps({
                "queue": "batch",
                "container": {"image": image, "flags": flags, "ssh": True},
            }))
            marker = root / "pbs-workbench" / "workbenches" / "00"
            marker.parent.mkdir(parents=True)
            marker.touch()
            module = root / "module"
            module.write_text("#!/bin/sh\nexit 0\n")
            module.chmod(0o755)
            with patch("job.workbench.files", return_value=resources), patch(
                "job.places.logs_folder", return_value=directory
            ):
                script = Path(workbench.jobscript_from_json(str(profile), str(marker)))
            self.addCleanup(script.unlink, missing_ok=True)
            job_id = f"test-{uuid.uuid4().hex}.server"
            env = {
                **os.environ, "HOME": directory, "PATH": f"{root}:{os.environ['PATH']}",
                "PBS_O_WORKDIR": directory, "PBS_JOBID": job_id,
            }
            log = root / "job.log"
            with log.open("w+") as output:
                process = subprocess.Popen(
                    ["bash", str(script)], env=env, stdout=output, stderr=output
                )
                try:
                    endpoint = None
                    for _ in range(150):
                        endpoint = workbench.running_container_ssh(str(marker), job_id)
                        if endpoint or process.poll() is not None:
                            break
                        time.sleep(0.2)
                    output.flush()
                    output.seek(0)
                    self.assertIsNotNone(endpoint, output.read())
                    known = root / "known_hosts"
                    known.write_text(endpoint["host_key_alias"] + " " + endpoint["host_public_key"] + "\n")
                    user = pwd.getpwuid(os.getuid()).pw_name
                    ssh = [
                        "ssh", "-F", "/dev/null", "-i", str(key), "-o", "IdentitiesOnly=yes",
                        "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known}",
                        "-o", f"HostKeyAlias={endpoint['host_key_alias']}", "-o", "BatchMode=yes",
                        "-o", "ConnectTimeout=3", "-p", str(endpoint["port"]),
                        f"{user}@127.0.0.1",
                    ]
                    result = subprocess.run(
                        ssh + ["id -u; cat /etc/debian_version"],
                        text=True, capture_output=True, timeout=15,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.splitlines()[0], str(os.getuid()))
                    self.assertTrue(result.stdout.splitlines()[1].startswith("12"))
                    self.assertIsInstance(endpoint["userns"], bool)
                    with socket.socket() as service:
                        service.bind(("127.0.0.1", 0))
                        service.listen(1)
                        service.settimeout(10)

                        def respond():
                            connection, _ = service.accept()
                            with connection:
                                connection.sendall(connection.recv(32))

                        thread = threading.Thread(target=respond, daemon=True)
                        thread.start()
                        forwarded = subprocess.run(
                            ssh[:-1] + ["-W", f"127.0.0.1:{service.getsockname()[1]}", ssh[-1]],
                            input=b"hello", capture_output=True, timeout=10,
                        )
                        thread.join(timeout=10)
                        self.assertFalse(thread.is_alive())
                        self.assertEqual(forwarded.returncode, 0, forwarded.stderr)
                        self.assertEqual(forwarded.stdout, b"hello")
                finally:
                    if process.poll() is None:
                        process.terminate()
                    process.wait(timeout=45)
                self.assertIsNone(workbench.running_container_ssh(str(marker), job_id))

    def test_pbs_script_starts_and_stops_ssh_helper(self):
        data_dir = Path(workbench.__file__).parent / "data"
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            resources = root / "resources"
            resources.mkdir()
            (resources / "idle.sh").write_text(
                (data_dir / "idle.sh").read_text().replace(
                    "sleep 30", 'cat "$CONTAINER_SSH_READY_FILE"; break'
                )
            )
            (resources / "sshd.py").write_text((data_dir / "sshd.py").read_text())
            keys = root / ".ssh"
            keys.mkdir(mode=0o700)
            key = root / "client"
            subprocess.run(
                ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True
            )
            (keys / "authorized_keys").write_text(key.with_suffix(".pub").read_text())
            (keys / "authorized_keys").chmod(0o600)
            profile = root / "profile.json"
            profile.write_text(json.dumps({
                "queue": "batch",
                "container": {"image": "image.sif", "flags": "", "ssh": True},
            }))
            marker = root / "pbs-workbench" / "workbenches" / "00"
            marker.parent.mkdir(parents=True)
            marker.touch()
            module = root / "module"
            module.write_text("#!/bin/sh\nexit 0\n")
            module.chmod(0o755)
            apptainer = root / "apptainer"
            apptainer.write_text(
                '#!/bin/sh\n'
                'if [ "$1" = exec ]; then shift 2; exec "$@"; fi\n'
                'exit 0\n'
            )
            apptainer.chmod(0o755)
            with patch("job.workbench.files", return_value=resources), patch(
                "job.places.logs_folder", return_value=directory
            ):
                script = Path(workbench.jobscript_from_json(str(profile), str(marker)))
            self.addCleanup(script.unlink, missing_ok=True)
            env = {
                **os.environ, "HOME": directory, "PATH": f"{root}:{os.environ['PATH']}",
                "PBS_O_WORKDIR": directory, "PBS_JOBID": "123.server",
            }
            result = subprocess.run(
                ["bash", str(script)], env=env, text=True, capture_output=True, timeout=30
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            endpoint = json.loads(result.stdout)
            self.assertEqual(endpoint["job_id"], "123.server")
            self.assertGreater(endpoint["port"], 0)
            self.assertTrue((root / "pbs-workbench" / "ssh" / "host_ed25519").is_file())
            self.assertFalse(marker.exists())
            self.assertIsNone(workbench.running_container_ssh(str(marker), "123.server"))
            (keys / "authorized_keys").unlink()
            marker.touch()
            failed = subprocess.run(
                ["bash", str(script)], env=env, text=True, capture_output=True, timeout=30
            )
            self.assertEqual(failed.returncode, 1)
            self.assertIn("authorized keys file not found", failed.stderr)
            self.assertFalse(marker.exists())
            self.assertFalse(Path(workbench.container_ready_dir(str(marker))).exists())

    def test_public_key_login_and_tcp_forwarding(self):
        helper = Path(workbench.__file__).parent / "data" / "sshd.py"
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            runtime = root / "runtime"
            runtime.mkdir(mode=0o700)
            client_key = root / "client"
            subprocess.run(
                ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(client_key)],
                check=True,
            )
            authorized = root / "authorized_keys"
            authorized.write_text(client_key.with_suffix(".pub").read_text())
            authorized.chmod(0o600)
            ready = root / "ready.json"
            daemon = subprocess.Popen(
                [sys.executable, str(helper), "123.server", str(ready), str(runtime),
                 str(root / "hostkeys"), str(authorized)],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            )
            try:
                for _ in range(100):
                    if ready.exists() or daemon.poll() is not None:
                        break
                    time.sleep(0.05)
                if not ready.exists():
                    self.fail("SSH daemon did not start")
                endpoint = json.loads(ready.read_text())
                known_hosts = root / "known_hosts"
                known_hosts.write_text(endpoint["host_key_alias"] + " " + endpoint["host_public_key"] + "\n")
                user = pwd.getpwuid(os.getuid()).pw_name
                ssh = [
                    "ssh", "-F", "/dev/null", "-i", str(client_key),
                    "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
                    "-o", f"UserKnownHostsFile={known_hosts}",
                    "-o", f"HostKeyAlias={endpoint['host_key_alias']}",
                    "-o", "BatchMode=yes", "-o", "ConnectTimeout=3",
                    "-p", str(endpoint["port"]), f"{user}@127.0.0.1",
                ]
                result = subprocess.run(ssh + ["id -u"], text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), str(os.getuid()))

                with socket.socket() as service:
                    service.bind(("127.0.0.1", 0))
                    service.listen(1)
                    service.settimeout(10)

                    def respond():
                        connection, _ = service.accept()
                        with connection:
                            connection.sendall(connection.recv(32))

                    thread = threading.Thread(target=respond)
                    thread.start()
                    result = subprocess.run(
                        ssh[:-1] + ["-W", f"127.0.0.1:{service.getsockname()[1]}", ssh[-1]],
                        input=b"hello", capture_output=True, timeout=10,
                    )
                    thread.join(timeout=10)
                    self.assertFalse(thread.is_alive())
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, b"hello")
            finally:
                if daemon.poll() is None:
                    daemon.terminate()
                _, error = daemon.communicate(timeout=10)
            self.assertEqual(daemon.returncode, 0, error)
            self.assertFalse(ready.exists())
