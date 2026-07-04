@echo off
title Stop Simulation
wsl -d Ubuntu-22.04 docker rm -f gbplanner_ref
pause
