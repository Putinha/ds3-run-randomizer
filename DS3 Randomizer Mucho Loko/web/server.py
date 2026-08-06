"""Small dependency-free web UI for the DS3 randomizer."""

import json
import os
import sys
import random

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse


# Project root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


from randomizer import generate_valid_seed, load_database
from full_run import generate_full_run


HOST = "127.0.0.1"
PORT = 8000


def build_result(result, areas, weapons, locations):
    """
    Convert the complete randomizer result into the small response
    needed by the web interface.

    The randomizer still generates the complete seed.
    The website only displays ONE randomized weapon.
    """

    rows = []

    for location_id, randomized in result["placements"].items():

        if location_id not in locations:
            continue

        location = locations[location_id]

        original = location.get("item")

        if original is None and location.get("items"):
            original = ", ".join(location["items"])

        rows.append({
            "location": location.get("name", location_id),
            "area": location.get("area", ""),
            "original": original or "",
            "randomized": randomized,
        })

    if not rows:
        raise ValueError(
            "Randomizer generated no weapon placements."
        )

    # Use the seed itself to select the preview weapon.
    # This makes the displayed weapon deterministic for that seed.
    preview_rng = random.Random(result["seed"])

    weapon = preview_rng.choice(rows)

    print("DEBUG WEAPON:", weapon)

    return {
        "seed": result["seed"],
        "valid": bool(result["validation"]["valid"]),
        "weapon_count": len(weapons),
        "placement_count": len(rows),
        "weapon": weapon,
    }


class Handler(BaseHTTPRequestHandler):

    def send_json(self, payload, status=200):
        body = json.dumps(
            payload,
            ensure_ascii=False
        ).encode("utf-8")

        self.send_response(status)

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )

        self.send_header(
            "Content-Length",
            str(len(body))
        )

        self.end_headers()

        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path

        # Main website
        if path == "/":
            self.send_file(
                "index.html",
                "text/html; charset=utf-8"
            )
            return

        # Randomizer configuration
        if path == "/api/config":
            self.send_json({
                "categories": [
                    {
                        "id": "weapons",
                        "name": "Weapons",
                        "available": True
                    },
                    {
                        "id": "shields",
                        "name": "Shields",
                        "available": False
                    },
                    {
                        "id": "armor",
                        "name": "Armor",
                        "available": False
                    },
                    {
                        "id": "rings",
                        "name": "Rings",
                        "available": False
                    },
                    {
                        "id": "spells",
                        "name": "Spells",
                        "available": False
                    }
                ]
            })
            return

        self.send_json(
            {"error": "Not found"},
            404
        )

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/full-run":
            self.handle_full_run()
            return

        if path != "/api/randomize":
            self.send_json(
                {"error": "Not found"},
                404
            )
            return

        try:
            # Read request body
            length = int(
                self.headers.get(
                    "Content-Length",
                    "0"
                )
            )

            if length > 4096:
                raise ValueError(
                    "Request too large"
                )

            raw_body = self.rfile.read(length)

            data = json.loads(
                raw_body or b"{}"
            )

            # Currently only weapons are implemented.
            categories = data.get(
                "categories",
                ["weapons"]
            )

            if categories != ["weapons"]:
                raise ValueError(
                    "Only Weapons is currently available."
                )

            # Seed
            seed = data.get("seed")

            if seed in (None, ""):
                seed = None

            else:
                if (
                    isinstance(seed, bool)
                    or not isinstance(seed, int)
                ):
                    raise ValueError(
                        "Seed must be a non-negative integer."
                    )

                if seed < 0:
                    raise ValueError(
                        "Seed must be a non-negative integer."
                    )

            # Load database
            areas, weapons, locations = load_database(ROOT)

            # Generate a progression-valid seed
            result = generate_valid_seed(
                seed=seed,
                base_dir=ROOT,
                max_attempts=1000
            )

            # Convert result to web response
            response = build_result(
                result,
                areas,
                weapons,
                locations
            )

            self.send_json(response)

        except (
            TypeError,
            ValueError,
            json.JSONDecodeError
        ) as exc:

            self.send_json(
                {"error": str(exc)},
                400
            )

        except Exception as exc:

            print(
                "SERVER ERROR:",
                repr(exc)
            )

            self.send_json(
                {
                    "error":
                    f"Randomization failed: {exc}"
                },
                500
            )

    def handle_full_run(self):
        try:
            length = int(
                self.headers.get(
                    "Content-Length",
                    "0"
                )
            )

            if length > 4096:
                raise ValueError(
                    "Request too large"
                )

            raw_body = self.rfile.read(length)

            data = json.loads(
                raw_body or b"{}"
            )

            seed = data.get("seed")

            if seed in (None, ""):
                seed = None

            result = generate_full_run(
                seed=seed,
                base_dir=ROOT
            )

            self.send_json(result)

        except (
            TypeError,
            ValueError,
            json.JSONDecodeError
        ) as exc:

            self.send_json(
                {"error": str(exc)},
                400
            )

        except Exception as exc:

            print(
                "SERVER ERROR:",
                repr(exc)
            )

            self.send_json(
                {
                    "error":
                    f"Full run generation failed: {exc}"
                },
                500
            )

    def send_file(self, filename, content_type):
        path = os.path.join(
            os.path.dirname(
                os.path.abspath(__file__)
            ),
            filename
        )

        try:
            with open(path, "rb") as file:
                body = file.read()

        except OSError:
            self.send_json(
                {"error": "Page not found"},
                404
            )
            return

        self.send_response(200)

        self.send_header(
            "Content-Type",
            content_type
        )

        self.send_header(
            "Content-Length",
            str(len(body))
        )

        self.end_headers()

        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(fmt % args)


if __name__ == "__main__":

    print(
        f"DS3 Randomizer: http://{HOST}:{PORT}"
    )

    server = HTTPServer(
        (HOST, PORT),
        Handler
    )

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        print("\nServer stopped.")

    finally:
        server.server_close()
