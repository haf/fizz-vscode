https://fizzbee.io/testing/tutorials/quick-start/

    fizzbee-mbt-server -states_file out/latest/
    go test ./fizztests
    go test -v ./fizztests
    go test -race ./fizztests

    # flags:
    # --max-seq-runs=0
    # --max-parallel-runs=0