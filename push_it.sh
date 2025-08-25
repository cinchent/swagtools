#!/usr/bin/env bash
THISDIR=$(cd "$(dirname "${BASH_SOURCE:-$0}")" && pwd -P)
cd "${THISDIR}" || exit 1
client=swagtools_skeleton_client
function gsta { git stash $@; }
function gco { git checkout $@; }
function gmxt { git merge -X theirs $@; }
function gau { git add -u $@; }
function gc { git commit $@; }
function gpus { git push $@; }
function is_gsta { [[ $(gsta | grep -ci 'No local changes') -eq 0 ]] && echo "true" || echo "false"; }

stashed=$(is_gsta)
cd $client && stashed_client=$(is_gsta)
gco develop && $stashed_client && gsta pop
cd .. && gco develop && $stashed && gsta pop
cd $client && gau && echo "client commit text" > /tmp/out && gc -e -F /tmp/out && gpus
cd .. && gau && echo "main commit text" > /tmp/out && gc -e -F /tmp/out && gpus
gco main && cd $client && gco main
gmxt develop && gpus
cd .. && gmxt develop && gpus
gco develop && cd $client && gco develop
./install.sh
cd ..
