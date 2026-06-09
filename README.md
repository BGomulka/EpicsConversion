# EpicsConversion
Python script to losslessly convert between Epics `.db` files and `.csv` files


## Usage Guide

By default, `EpicsConversion.py` works wthin your current working directory. The script requires either the argument `--cd` (Process `.csv` to `.db`) or `--dc` (Process `.db to `.db`) to run.

To test the script with extra details, run it in test mode. This will only process files that begin with the word "test":
```bash
python3 EpicsConversion.py --cd -t -v
```
For a quick reference guide, run:
```bash
python3 EpicsConversion.py -h
