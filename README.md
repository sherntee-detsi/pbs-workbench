# pbs-workbench

Start a PBS job that runs idle to ssh into and work interactively. 

## Installation

### As a module

If you are a member of the gb02 project, you can use pbs-workbench by loading the module

```sh
module use /g/data/gb02/public/modules
module load pbs-workbench
```

You can add those lines to your .bashrc file if you want the module to be always available. 
This is a requirement if you want to to use the [vscode extension](https://github.com/eliocamp/pbs-workbench-vscode). 

### Binary

Alternatively, you can download the latest single-file binary from https://github.com/eliocamp/pbs-workbench/releases/latest/download/job and save it to somewhere on your PATH.
For example:

```sh
wget -O ~/bin/job https://github.com/eliocamp/pbs-workbench/releases/latest/download/job 
```

And make sure that `~/bin/job` is in your PATH by adding this to your .bashrc file:

```
prepend_path PATH ${HOME}/bin
```

This is a requirement if you want to to use the [vscode extension](https://github.com/eliocamp/pbs-workbench-vscode). 

Note that this was compiled on gadi and it's not tested in any other platform.

### uv

With [uv](https://docs.astral.sh/uv/) installed, install the `job` command from GitHub:

```sh
uv tool install git+https://github.com/sherntee-detsi/pbs-workbench.git
```

The package requires Python 3.12 or newer.

### pipx

Alternatively alternatively, you can install it with pipx.
First you'll need to [install pipx](https://pipx.pypa.io/stable/how-to/install-pipx/).

```sh
module load python3/3.12.1   # The default version on gadi is too old
python3 -m venv ~/.local/share/pipx-venv
~/.local/share/pipx-venv/bin/pip install pipx
ln -s ~/.local/share/pipx-venv/bin/pipx ~/.local/bin/pipx
pipx ensurepath
```

And then install pbs-workbench with

```sh
pipx install git+https://github.com/eliocamp/pbs-workbench.git
```

To uninstall, run 

```sh
pipx unsintall pbs-workbench
```

## Quick Start

0. **Create a profile** (first time only):

```sh
job profile
```

This will open the Profile Editor with some defaults. 

```
───────────────────────────────────────────────────────────────────────────────────────
                              PBS Workbench Profile Editor
───────────────────────────────────────────────────────────────────────────────────────
  < Job * >  < Advanced >  < Container >

 Name:     default
 Queue:    < normal >  (left/right)
 Project:  lo70
 CPUs:     8
 RAM:      32GB
 Walltime: 8:00:00
───────────────────────────────────────────────────────────────────────────────────────
  < Save >    < Quit >
```

Use the UI to configure job requirements (CPUs, memory, walltime, etc.). 
The queue choices come from PBS; use left and right to select a queue. A saved
queue no longer reported by PBS remains selected and is marked in the editor.
Jobfs and Storage are optional and initially empty; use Advanced to edit them.
In the Container tab, set an Apptainer image and optional flags to start a
job-specific instance. Leave Image empty to run without a container. Flags
support shell-style quoting but not shell expansion.
If you want to create more than one profile, you can run `job profile profile_name` to create a new profile with a name "profile_name".
If profile_name already exists, this will let you edit it. 

### Migration guide

If you are updating from the old 1.0 version, you need to migrate your profiles by running `job profile profile_name`. 
If only an old version of the profile exists, it's information will be used to prepopulate the new profile UI. 
Check that everything is correct and save the new profile. 

1. **Start a job**:

```sh
job start
```

This will start the `default` profile. You can start a different one with `job start profile_name`.

2. **Monitor your job**:
 
The monitor starts automatically, showing job status and connection instructions. 
You can safely close the monitor with `Ctrl + C` and restart it with 

```sh
job monitor
```

3. **End your job**:

To end the job early use 

```sh
job end
```

## Connecting to the workbench

You can connect to the workbench using SSH using the commands shown in the monitor. 

Once the job starts, the monitor show something like this: 

```
─────────────────────────────────────────────────────────────────────────────────────────
                                   PBS Workbench Monitor
───────────────────────────────────────────────────────────────────────────────────────── 
 Job ID: 170258723.gadi-pbs                                                             
 Usage: 15 SU                                                                           
 Running on node gadi-cpu-clx-0428                                                      
                                                                                        
 SSH command:                                                                           
    ssh -X xxxxx@gadi-cpu-clx-0428                                                  
 SSH tunnel:                                                                            
    ssh -L 8080:127.0.0.1:8080 xxxxx@gadi-cpu-clx-0428                                
 Remote-ssh:                                                                            
    --remote ssh-remote+gadi-cpu-clx-0428 /home/565/xxxxx     
 Jupyter Lab:                         
    ssh -t -L 8080:127.0.0.1:8080 xxxxx@gadi-cpu-clx-0428 "module load jupyterlab/3.4.3-py3.9 && jupyter lab --no-browser --port=8080"  


         00:57:52                    Progress: 12 %                    07:02:08         
            0.0GB                      Memory: 0 %                     32.0GB           
                                        CPU: 0 %                                        
─────────────────────────────────────────────────────────────────────────────────────────

```

The monitor will tell you the status of the job and the compute node where it's running. 
It will also show you convenient commands that you can copy to connect directly to the compute node via SSH, create an SSH tunnel or connect in VSCode with the Remote-SSH extension. 
For a container-enabled job, it also shows a command to SSH to the node and
open a shell in the Apptainer instance once the instance has started. This
shell command does not itself configure VS Code Remote-SSH inside the container.
The bars wil show you your used and remaining time, as well as CPU usage and memory usage reported by `qstat`. 
If you consistently underuse your CPU, consider requesting a smaller job. 

### SSH

In a terminal **in your local machine**: 

Use the SSH command to ssh into the node: 

```sh
ssh -X xxxxx@gadi-cpu-clx-0428
```

### VScode and similar IDEs

To use a IDE that supports the Remote SSH extension, like VSCode or its forks, first you need to set up the proxy jump [as explained here](https://21centuryweather.github.io/21st-Century-Weather-Software-Wiki/gadi/vscode.html#configure-ssh-only-once). 

After that setup, you can install the [companion extension](https://github.com/eliocamp/pbs-workbench-vscode). 
It will add commands to start and stop Workbenches as well as a command to connect to it via Remote SSH extension. 

Alternatively, you can use the "Remote-ssh" command provided by the monitor. 
Open a new terminal in your local machine, write your editor's command followed by the remote-ssh command.

For example, to use vscode, use 

```sh
code --remote ssh-remote+gadi-cpu-clx-0428 /home/565/xxxxx
```

For Positron, use

```sh
positron --remote ssh-remote+gadi-cpu-clx-0428 /home/565/xxxxx
```

This will open the editor, connect to the remote node, and open the current directory. 

### VS Code Remote-SSH inside an Apptainer container

Container SSH is opt-in. The supplied `containers/vscode.def` builds a Debian
image with the Linux libraries, OpenSSH server, Python 3, Bash, tar and curl
needed for the helper and VS Code Server. From a checkout on a machine that
can build Apptainer images, run:

```sh
apptainer build --fakeroot vscode.sif containers/vscode.def
```

Use a cluster-supported build method if fakeroot is unavailable, and place the
resulting SIF on storage accessible from the compute node. A custom image or
registry image can also be used if it has those prerequisites, the job user's
account and login shell, and a writable home directory. The host kernel must
meet [VS Code's Linux requirements](https://code.visualstudio.com/docs/remote/linux).
The job binds `$HOME` into the instance; incompatible bind or network-isolation
flags can prevent SSH from working.

1. In `job profile`, open **Container**, set Image to the image path or URI,
   optionally set Flags, and select **Enable VS Code SSH**. Start the job.
2. Ensure the job owner's `~/.ssh/authorized_keys` contains the public key
   from your local SSH client, and that your home, `.ssh` directory and key
   file have permissions acceptable to OpenSSH `StrictModes`.
3. When the monitor says container SSH is ready, run `job ssh-config` on the
   cluster login node. Copy its output to your local `~/.ssh/config`, before
   any general `Host *` rules. Configure SSH on your local machine so the
   compute hostname in the generated `ProxyCommand` is reachable through the
   login node, for example via an existing `ProxyJump` rule. The compute-node
   SSH server must permit TCP forwarding.
4. Connect to `pbs-workbench` using VS Code's Remote-SSH extension. At the
   first host-key prompt, compare the fingerprint with the one printed by
   `job ssh-config` before accepting it. VS Code installs its server into the
   bound home; if the compute node has no internet access, configure the
   extension's local-download fallback.

The endpoint and port change with each job: rerun `job ssh-config` and update
the local entry after starting another job. The host key is persistent in the
user-private `~/pbs-workbench/ssh/` directory. The listener binds only to the
compute node's loopback interface and uses public-key authentication, but
other local users can still reach it. Its unprivileged SSH server runs with
`UsePAM no`, so it does not apply the host's PAM/MFA or session policies.
Confirm this is permitted with the cluster administrator, and verify that the
SSH session and VS Code processes remain in the job's PBS cgroup. The
companion extension's existing compute-node connection is not automatically
redirected into the container.

### Jupyter lab

To run jupyter lab, **in your local machine** run the Jupyter Lab  command:  

```sh
ssh -t -L 8080:127.0.0.1:8080 xxxxx@gadi-cpu-clx-0428 "module load jupyterlab/3.4.3-py3.9 && jupyter lab --no-browser --port=8080"  
```

This will open a tunnel into the compute node and start jupyter lab.
You'll see this meessage

```
    To access the server, open this file in a browser:
        file:///home/565/xxxxx/.local/share/jupyter/runtime/jpserver-2280832-open.html
    Or copy and paste one of these URLs:
        http://localhost:8080/lab?token=d37446af8d37c5379d60c64319506fb218990f085ad54485
     or http://127.0.0.1:8080/lab?token=d37446af8d37c5379d60c64319506fb218990f085ad54485
```

Open any of the two last links in a browser and done!

**Important**: Closing the terminal will terminate the tunnel and your jupyterlab session. 

## More details 

### Project File

PBS Workbench tracks your running job using the file `~/pbs-workbench/workbenches/00`, which contains the job ID of the current job. 
Don't edit or delete that file. 

### Log Files

Job output is saved to `~/pbs-workbench/logs/` with files named:

- `{job_id}.gadi-pbs.OU` (standard output)
- `{job_id}.gadi-pbs.ER` (standard error)


## Limitations

Currently, only one job can be run at a time. 
