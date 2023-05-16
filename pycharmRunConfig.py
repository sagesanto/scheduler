import sys

if __name__ == '__main__':
    fname = sys.argv[1]
    exec(open(fname).read())