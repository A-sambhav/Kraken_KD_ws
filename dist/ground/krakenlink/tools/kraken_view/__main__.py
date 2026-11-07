"""Launch the local KrakenSDR raw viewer."""
import argparse
import time
import webbrowser


def main(argv=None):
    parser = argparse.ArgumentParser(description="Live raw-data viewer for KrakenSDR RTL-SDR channels")
    parser.add_argument("--freq", type=float, default=433.0, help="center frequency in MHz (default 433.0)")
    parser.add_argument("--gain", type=float, default=28.0, help="tuner gain in dB")
    parser.add_argument("--rate", type=float, choices=(1.024, 2.048, 2.4), default=2.4, help="sample rate in MS/s")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--fake", action="store_true", help="use simulated IQ sources; requires no hardware")
    parser.add_argument("--fake-dead", type=int, metavar="N", help="make channel N report NO DATA in fake mode")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = parser.parse_args(argv)
    if args.fake_dead is not None and not args.fake:
        parser.error("--fake-dead requires --fake")
    from .source import make_readers
    from .app import create_app
    readers = make_readers(args.fake, args.fake_dead, args.freq, int(round(args.gain * 10)), int(args.rate * 1e6))
    app = create_app(readers, 5 if args.fake else len(readers), args.freq, int(round(args.gain * 10)), int(args.rate * 1e6))
    if not args.no_browser:
        webbrowser.open(f"http://127.0.0.1:{args.port}")
    try:
        app.run(host="127.0.0.1", port=args.port, debug=False)
    except KeyboardInterrupt:
        pass
    finally:
        for reader in readers: reader.close()


if __name__ == "__main__":
    main()
