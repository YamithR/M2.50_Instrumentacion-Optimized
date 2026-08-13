# main.py — Punto de entrada del script M2.50 DAQ (PySide6).
# Uso:  python main.py

import sys

from PySide6.QtWidgets import QApplication

from app.window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("M2.50 DAQ")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
