"""Compatibility CLI when running from a Hermes repository checkout."""

from gpt_companion.inspect import main


if __name__ == "__main__":
    raise SystemExit(main())
