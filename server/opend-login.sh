#!/bin/bash
# Log in to moomoo OpenD on the server. Run inside tmux so it keeps running:
#   tmux new -A -s opend /opt/go-halal/server/opend-login.sh
# OpenD asks for your moomoo ID, password and (first time) the SMS code; you type them.
# After one successful login you can restart without the password:
#   /opt/go-halal/server/opend-login.sh <moomoo ID>
cd /opt/opend/moomoo_OpenD_*/moomoo_OpenD_*_Ubuntu18.04 || exit 1
if [ -n "$1" ]; then
  ./OpenD -login_account="$1" -login_by_remember=1 -console=1 -lang=en
else
  ./OpenD -console=1 -lang=en
fi
echo "OpenD stopped. Press Enter to close."; read -r
