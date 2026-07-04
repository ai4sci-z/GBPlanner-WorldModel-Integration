@echo off
title GBPlanner Keepalive - DO NOT CLOSE
start "GBPlanner-Sim" cmd /k wsl -d Ubuntu-22.04 bash /mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/gbplanner_ref/run_light.sh
echo This window keeps WSL alive. DO NOT CLOSE while demoing.
wsl -d Ubuntu-22.04 sleep 86400
