#! /bin/bash

LL="120"


doItHere()
{
    black --line-length "$LL" *.py
    pylama --max-line-length="$LL" *.py
}

doIt()
{
    black --line-length "$LL" .
    pylama --max-line-length="$LL" .
}

main()
{
    pip list | grep black || {
        pip install black pylama setuptools
    }

    # always reformat the project
    ( cd pSwai && doIt )

    # if there are any local python files in this dir format them but only them
    ls *.py >/dev/null 2>/dev/null && {
        doItHere
    }
}

main
