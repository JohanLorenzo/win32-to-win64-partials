# win32-to-win64-partials

## Set up

```sh
ssh buildbot-master85.bb.releng.scl3.mozilla.com
sudo su - ctlbld
mkdir bug-xxxxxx && cd bug-xxxxxx
git clone https://github.com/JohanLorenzo/win32-to-win64-partials

# Modify runme.py to point to $TO_VERSION

# Fill the creds in config.yml. You can find them in /builds/releaserunner/release-runner.ini

ln -s /builds/releaserunner/id_rsa .

source /builds/releaserunner/bin/activate
python runme.py

# If the graph is printed out, uncomment the last line of runme.py
python runme.py
```

## Risks
