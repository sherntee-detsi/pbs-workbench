# PBS Workbench: VS Code in an Apptainer container

PBS Workbench starts a PBS job with an Apptainer instance and an optional SSH
server inside it. VS Code Remote-SSH connects through the cluster login and
compute nodes, so the VS Code Server runs in the container rather than in the
compute node's host environment.

The previous documentation is available in [README.legacy.md](README.legacy.md).

## Prerequisites

- On the cluster: PBS commands, Apptainer available via `module load apptainer`,
  a shared writable home directory, and Python 3.12 or newer for `job`.
- On your computer: an SSH client, VS Code, and the
  [Remote - SSH extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh).
- SSH access from your computer through the login node to the allocated compute
  node. The compute-node SSH server must allow TCP forwarding.
- The [VS Code Linux requirements](https://code.visualstudio.com/docs/remote/linux)
  must be met, including by the compute node's kernel (`uname -r`).

Container SSH uses your cluster account's `~/.ssh/authorized_keys`. Ensure it
contains the public key used by your local SSH client, and that your home
directory, `~/.ssh`, and `authorized_keys` satisfy OpenSSH `StrictModes`.
For example, on the cluster:

```sh
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

If you do not already have a key, generate one locally with `ssh-keygen` and
install its **public** key in the cluster account's `authorized_keys` using
your site's approved procedure. Never copy the private key to the cluster.

## 1. Install PBS Workbench

On the cluster login node, install with [uv](https://docs.astral.sh/uv/):

```sh
uv tool install git+https://github.com/sherntee-detsi/pbs-workbench.git
```

Alternatively, install from a checkout with `pipx install .`. Ensure `job`
is on your `PATH`. If updating an existing uv installation, run
`uv tool upgrade job`.

## 2. Configure access to compute nodes

On your computer, configure SSH to reach compute nodes through the cluster
login node. Adapt this example to your site's actual login hostname, username,
compute-node hostname pattern, and identity:

```sshconfig
Host cluster-login
    HostName login.example.org
    User YOUR_USERNAME
    IdentityFile ~/.ssh/id_ed25519

Host compute-*
    User YOUR_USERNAME
    ProxyJump cluster-login
    IdentityFile ~/.ssh/id_ed25519
```

Save this in your local `~/.ssh/config`. The compute-node `Host` pattern must
match the hostname shown by the job monitor. Confirm that SSH to the allocated
node works with your site's authentication requirements. The generated
container configuration in step 4 uses a separate `ProxyCommand` to forward
through this compute-node connection.

## 3. Configure and start a container job

On the login node, run:

```sh
job profile
```

In **Job**, choose the PBS queue with left/right and set the requested
resources. Optional Jobfs and Storage entries are under **Advanced**. In
**Container**:

1. Set **Image** to a SIF path accessible on the compute node, or a registry
   URI. The available image for this cluster is:

   ```text
   oras://registry.git.dnr.qld.gov.au/hpc-shared-code/cluster-registry:test-vscode-latest
   ```

2. Leave **Flags** empty unless your site or image requires additional
   Apptainer options. Flags use shell-style quoting, but shell variables are
   not expanded.
3. Select **Enable VS Code SSH**, then save the profile.

The compute node must be able to access the registry and any required
credentials when using a URI. If it cannot, pull the image to shared storage
using your site's approved procedure and use the SIF path instead.

Start the default profile:

```sh
job start
```

For a named profile use `job profile NAME` and `job start NAME`. Wait for the
monitor to report that container SSH is ready. Select **Leave Running In
Background** to close the monitor without ending the job and print its job ID.
`Ctrl+C` also closes the monitor. Reopen it with `job monitor`.

## 4. Connect VS Code

On the login node, while the job is running:

```sh
job ssh-config
```

Copy the output into your **local** `~/.ssh/config`, before any general
`Host *` rules. It defines `Host pbs-workbench` with the job's current port,
host-key alias and compute-node proxy. If your local key is not selected
automatically, add an `IdentityFile` line to that block. Do not copy the
example compute-node rule over the generated block.

In VS Code, run **Remote-SSH: Connect to Host...** and select
`pbs-workbench`. On the first connection, compare the SSH host-key
fingerprint in the prompt with the fingerprint printed by `job ssh-config`
before accepting it. VS Code installs its server into the writable home
directory bound into the container. If the compute node cannot download it,
configure Remote-SSH's local-download fallback.

The job port and compute node may change each time. After starting a new job,
run `job ssh-config` again and replace the old local `Host pbs-workbench`
block. The existing companion extension's compute-node connection is not
automatically redirected into the container.

## 5. Finish or troubleshoot

Run `job end` or `job stop` on the login node to end the job. The monitor also displays a
command for an interactive Apptainer shell once the instance is ready.

If container SSH does not become ready, check the PBS job output in
`~/pbs-workbench/logs/`, image and registry access, `authorized_keys`
permissions, and the `apptainer` module. If SSH fails after readiness, check
compute-node connectivity, port forwarding and the local identity. Network
isolation or conflicting bind flags can prevent this setup from working.

The listener is bound only to the compute node's loopback interface and uses
public-key authentication, but other users on that node can reach the
listener. Its unprivileged SSH server runs with **`UsePAM no`** and therefore
does not enforce the host's PAM/MFA or session policies. Confirm this is
permitted with your cluster administrator, and verify that the SSH session
and VS Code processes remain in the job's PBS cgroup. Real PBS and VS Code
integration has not yet been verified on the target cluster.

## Building or customizing the image

The provided [definition file](containers/vscode.def) builds a Debian image:

```sh
apptainer build --fakeroot vscode.sif containers/vscode.def
```

Use a cluster-supported build method if fakeroot is unavailable. A custom
image needs Python 3 at `/usr/bin/python3`, OpenSSH server at `/usr/sbin/sshd`,
`ssh-keygen`, `/run/sshd`, Bash, tar, curl or wget, compatible glibc and
libstdc++, and the job user's account and login shell. `$HOME` is explicitly
bound into the instance when container SSH is enabled. Apptainer uses the
host kernel.
