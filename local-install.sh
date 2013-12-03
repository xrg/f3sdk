#!/bin/bash
set -e

# This script installs the SDK at the user's home

pushd $(dirname $0)
    install -d ~/bin/
    install bin/* ~/bin/

    install -d ~/.local/lib/f3sdk/
    rsync -a lib/ ~/.local/lib/f3sdk/

    cat '-' << "EOF" > ~/bin/f3-modulize
#!/bin/bash

exec ~/.local/lib/f3sdk/modulize.py "$@"
EOF

    chmod ug+x ~/bin/f3-modulize

popd

echo "All scripts and data installed!"
#eof