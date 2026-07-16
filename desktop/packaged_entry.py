"""Minimal frozen entry point; freeze support must run before importing the application."""

import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from desktop.launcher import main

    main()
