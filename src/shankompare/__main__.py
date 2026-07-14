"""Entry point for ``python -m shankompare``."""


def main() -> None:
    from shankompare.ui.app import run

    raise SystemExit(run())


if __name__ == "__main__":
    main()
