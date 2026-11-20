INSTANCE_STARTED=0

cleanup() {
    if [ "${INSTANCE_STARTED:-}" = "1" ]; then
        apptainer instance stop "$INSTANCE_NAME"
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
    module load apptainer || exit $?
    apptainer instance start "${CONTAINER_FLAGS[@]}" "$CONTAINER_IMAGE" "$INSTANCE_NAME" || exit $?
    INSTANCE_STARTED=1
fi

while true; do
    sleep 30  
done

exit 0
