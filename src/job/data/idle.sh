INSTANCE_STARTED=0

cleanup() {
    if [ -n "${CONTAINER_SSH_PID:-}" ]; then
        kill "$CONTAINER_SSH_PID" 2>/dev/null || true
    fi
    if [ -n "${CONTAINER_SSH_READY_FILE:-}" ]; then
        rm -f -- "$CONTAINER_SSH_READY_FILE"
    fi
    if [ -n "${CONTAINER_READY_FILE:-}" ]; then
        rm -f -- "$CONTAINER_READY_FILE"
    fi
    if [ "${INSTANCE_STARTED:-}" = "1" ]; then
        apptainer instance stop "$INSTANCE_NAME"
    fi
    if [ -n "${CONTAINER_SSH_PID:-}" ]; then
        wait "$CONTAINER_SSH_PID" 2>/dev/null || true
    fi
    if [ -n "${CONTAINER_SSH_RUNTIME:-}" ]; then
        rm -f -- "$CONTAINER_SSH_RUNTIME/sshd.py" "$CONTAINER_SSH_RUNTIME/sshd_config"
        rmdir -- "$CONTAINER_SSH_RUNTIME" 2>/dev/null || true
    fi
    if [ -n "${CONTAINER_READY_FILE:-}" ]; then
        rmdir -- "$CONTAINER_READY_DIR" 2>/dev/null || true
    fi
    if [ -f "$WORKBENCH_FILE" ]; then
        rm "$WORKBENCH_FILE"
    fi
}

trap cleanup EXIT
trap 'exit 143' SIGTERM

if [ -n "$CONTAINER_IMAGE" ]; then
    : "${PBS_JOBID:?PBS_JOBID is not set}"
    INSTANCE_NAME="pbs-workbench-${PBS_JOBID//[^a-zA-Z0-9._-]/_}"
    CONTAINER_READY_FILE="$CONTAINER_READY_DIR/$INSTANCE_NAME"
    module load apptainer || exit $?
    START_FLAGS=("${CONTAINER_FLAGS[@]}")
    if [ "$CONTAINER_SSH_ENABLED" = 1 ]; then
        : "${HOME:?HOME is not set}"
        CONTAINER_SSH_RUNTIME="$CONTAINER_READY_DIR/.$INSTANCE_NAME.ssh"
        CONTAINER_SSH_READY_FILE="$CONTAINER_READY_DIR/$INSTANCE_NAME.ssh.json"
        (umask 077; mkdir -p -- "$CONTAINER_SSH_RUNTIME" &&
            printf '%s\n' "$CONTAINER_SSH_SOURCE" > "$CONTAINER_SSH_RUNTIME/sshd.py") || exit $?
        START_FLAGS+=(--bind "$HOME:$HOME")
    fi
    apptainer instance start "${START_FLAGS[@]}" "$CONTAINER_IMAGE" "$INSTANCE_NAME" || exit $?
    INSTANCE_STARTED=1
    (umask 077; mkdir -p -- "$CONTAINER_READY_DIR" &&
        printf '%s\n' "$PBS_JOBID" > "$CONTAINER_READY_FILE") || exit $?
    if [ "$CONTAINER_SSH_ENABLED" = 1 ]; then
        rm -f -- "$CONTAINER_SSH_READY_FILE"
        JOIN_FLAGS=()
        if ! apptainer exec "instance://$INSTANCE_NAME" /usr/bin/python3 -c pass >/dev/null 2>&1; then
            JOIN_FLAGS+=(--userns)
        fi
        apptainer exec "${JOIN_FLAGS[@]}" "instance://$INSTANCE_NAME" /usr/bin/python3 \
            "$CONTAINER_SSH_RUNTIME/sshd.py" "$PBS_JOBID" "$CONTAINER_SSH_READY_FILE" \
            "$CONTAINER_SSH_RUNTIME" "$HOME/pbs-workbench/ssh" "$HOME/.ssh/authorized_keys" \
            "${JOIN_FLAGS:+userns}" &
        CONTAINER_SSH_PID=$!
        for ((attempt = 0; attempt < 30; attempt++)); do
            [ -s "$CONTAINER_SSH_READY_FILE" ] && break
            if ! kill -0 "$CONTAINER_SSH_PID" 2>/dev/null; then
                echo "Container SSH failed to start." >&2
                exit 1
            fi
            sleep 1
        done
        if [ ! -s "$CONTAINER_SSH_READY_FILE" ]; then
            echo "Timed out waiting for container SSH." >&2
            exit 1
        fi
    fi
fi

while true; do
    if [ -n "${CONTAINER_SSH_PID:-}" ] && ! kill -0 "$CONTAINER_SSH_PID" 2>/dev/null; then
        echo "Container SSH exited unexpectedly." >&2
        exit 1
    fi
    sleep 30  
done

exit 0
