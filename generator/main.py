"""Точка входа генератора.

    python -m generator.main generate   создать схемы и наполнить данными
    python -m generator.main drop       удалить схемы и данные
"""

import sys

from generator.app.generator import drop_all, run

COMMANDS = ("generate", "drop")


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "generate"

    if command not in COMMANDS:
        print(f"неизвестная команда: {command}; доступны: {', '.join(COMMANDS)}")
        return 2

    if command == "generate":
        run()
    else:
        drop_all()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
