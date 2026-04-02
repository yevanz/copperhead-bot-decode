#!/usr/bin/env python3
"""
CopperHead Bot Template - Your custom Snake game AI.

This bot connects to a CopperHead server and plays Snake autonomously.
Modify the calculate_move() function to implement your own strategy!

QUICK START
-----------
1. Install dependencies:   pip install -r requirements.txt
2. Run:                     python mybot.py --server ws://localhost:8765/ws/

For Codespaces, use the wss:// URL shown in the terminal, e.g.:
    python mybot.py --server wss://your-codespace-url.app.github.dev/ws/

WHAT TO CHANGE
--------------
The calculate_move() function (around line 200) is where your bot decides
which direction to move. The default strategy is simple: chase the nearest
food while avoiding walls and snakes. You can make it smarter!

Ideas for improvement:
  - Avoid getting trapped in dead ends (flood fill)
  - Predict where the opponent will move
  - Use different strategies based on snake length
  - Block the opponent from reaching food
"""

import asyncio
import json
import argparse
import random
import websockets


# ============================================================================
#  BOT CONFIGURATION - Change these to customize your bot
# ============================================================================

# The CopperHead server to connect to. Set this to your server's URL so you
# don't need to pass --server every time. Use "ws://" for local servers or
# "wss://" for Codespaces/remote servers.
GAME_SERVER = "ws://localhost:8765/ws/"

# Your bot's display name (shown to all players in the tournament)
BOT_NAME = "Yevanz"

# How your bot appears in logs
BOT_VERSION = "1.0"


# ============================================================================
#  BOT CLASS - Handles connection and game logic
# ============================================================================

class MyBot:
    """A CopperHead bot that connects to the server and plays Snake."""

    def __init__(self, server_url: str, name: str = None):
        self.server_url = server_url
        self.name = name or BOT_NAME
        self.player_id = None
        self.game_state = None
        self.running = False
        self.room_id = None
        # Grid dimensions (updated automatically from server)
        self.grid_width = 30
        self.grid_height = 20

    def log(self, msg: str):
        """Print a message to the console."""
        print(msg.encode("ascii", errors="replace").decode("ascii"))

    # ========================================================================
    #  CONNECTION - You probably don't need to change anything below here
    #  until you get to calculate_move()
    # ========================================================================

    async def wait_for_open_competition(self):
        """Wait until the server is reachable, then return.
        
        Bots always join the lobby regardless of competition state —
        the lobby is always available and the bot will wait there until
        the next competition starts.
        """
        import aiohttp

        base_url = self.server_url.rstrip("/")
        if base_url.endswith("/ws"):
            base_url = base_url[:-3]
        # Convert ws:// to http:// for the REST API
        http_url = base_url.replace("ws://", "http://").replace("wss://", "https://")

        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{http_url}/status") as resp:
                        if resp.status == 200:
                            self.log("Server reachable - joining lobby...")
                            return True
                        else:
                            self.log(f"Server not ready (status {resp.status}), waiting...")
            except Exception as e:
                self.log(f"Cannot reach server: {e}, retrying...")

            await asyncio.sleep(5)

    async def connect(self):
        """Connect to the game server."""
        await self.wait_for_open_competition()

        base_url = self.server_url.rstrip("/")
        if base_url.endswith("/ws"):
            base_url = base_url[:-3]
        url = f"{base_url}/ws/join"

        try:
            self.log(f"Connecting to {url}...")
            self.ws = await websockets.connect(url)
            self.log("Connected! Joining lobby...")
            # Send join message to enter the lobby
            await self.ws.send(json.dumps({
                "action": "join",
                "name": self.name
            }))
            return True
        except Exception as e:
            self.log(f"Connection failed: {e}")
            return False

    async def play(self):
        """Main game loop. Runs until disconnected or eliminated."""
        if not await self.connect():
            self.log("Failed to connect. Exiting.")
            return

        self.running = True

        try:
            while self.running:
                message = await self.ws.recv()
                data = json.loads(message)
                await self.handle_message(data)
        except websockets.ConnectionClosed:
            self.log("Disconnected from server.")
        except Exception as e:
            self.log(f"Error: {e}")
        finally:
            self.running = False
            try:
                await self.ws.close()
            except Exception:
                pass
            self.log("Bot stopped.")

    async def handle_message(self, data: dict):
        """Process messages from the server and respond appropriately."""
        msg_type = data.get("type")

        if msg_type == "error":
            self.log(f"Server error: {data.get('message', 'Unknown error')}")
            self.running = False

        elif msg_type == "joined":
            # Server assigned us a player ID and room
            self.player_id = data.get("player_id")
            self.room_id = data.get("room_id")
            self.log(f"Joined Arena {self.room_id} as Player {self.player_id}")

            # Tell the server we're ready to play
            await self.ws.send(json.dumps({
                "action": "ready",
                "mode": "two_player",
                "name": self.name
            }))
            self.log(f"Ready! Playing as '{self.name}'")

        elif msg_type == "state":
            # Game state update - this is where we decide our next move
            self.game_state = data.get("game")
            grid = self.game_state.get("grid", {})
            if grid:
                self.grid_width = grid.get("width", self.grid_width)
                self.grid_height = grid.get("height", self.grid_height)

            if self.game_state and self.game_state.get("running"):
                direction = self.calculate_move()
                if direction:
                    await self.ws.send(json.dumps({
                        "action": "move",
                        "direction": direction
                    }))

        elif msg_type == "start":
            self.log("Game started!")

        elif msg_type == "gameover":
            winner = data.get("winner")
            my_wins = data.get("wins", {}).get(str(self.player_id), 0)
            opp_id = 3 - self.player_id
            opp_wins = data.get("wins", {}).get(str(opp_id), 0)
            points_to_win = data.get("points_to_win", 5)

            if winner == self.player_id:
                self.log(f"Won! (Score: {my_wins}-{opp_wins}, first to {points_to_win})")
            elif winner:
                self.log(f"Lost! (Score: {my_wins}-{opp_wins}, first to {points_to_win})")
            else:
                self.log(f"Draw! (Score: {my_wins}-{opp_wins}, first to {points_to_win})")

            # Signal ready for next game in the match
            await self.ws.send(json.dumps({
                "action": "ready",
                "name": self.name
            }))

        elif msg_type == "match_complete":
            winner_id = data.get("winner", {}).get("player_id")
            winner_name = data.get("winner", {}).get("name", "Unknown")
            final_score = data.get("final_score", {})
            my_score = final_score.get(str(self.player_id), 0)
            opp_id = 3 - self.player_id
            opp_score = final_score.get(str(opp_id), 0)

            if winner_id == self.player_id:
                self.log(f"Match won! Final: {my_score}-{opp_score}")
                self.log("Waiting for next round...")
            else:
                self.log(f"Match lost to {winner_name}. Final: {my_score}-{opp_score}")
                self.log("Eliminated. Exiting.")
                self.running = False

        elif msg_type == "match_assigned":
            # Assigned to a new match in the next tournament round
            self.room_id = data.get("room_id")
            self.player_id = data.get("player_id")
            self.game_state = None
            opponent = data.get("opponent", "Opponent")
            self.log(f"Next round! Arena {self.room_id} vs {opponent}")
            # Signal ready to the server
            await self.ws.send(json.dumps({"action": "ready", "name": self.name}))

        elif msg_type in ("lobby_joined", "lobby_update"):
            # In the lobby waiting for the competition to start
            if msg_type == "lobby_joined":
                self.log(f"Joined lobby as '{data.get('name', self.name)}'")

        elif msg_type in ("lobby_left", "lobby_kicked"):
            self.log("Removed from lobby.")
            self.running = False

        elif msg_type == "competition_complete":
            champion = data.get("champion", {}).get("name", "Unknown")
            self.log(f"Tournament complete! Champion: {champion}")
            self.running = False

        elif msg_type == "waiting":
            self.log("Waiting for opponent...")

    # ========================================================================
    #  YOUR AI STRATEGY - Modify calculate_move() to change how your bot plays
    # ========================================================================

    def calculate_move(self) -> str | None:
        """Decide which direction to move.

        IMPROVED STRATEGY for better winning chances:
        1. Prioritize capturing food while maintaining safety
        2. Block opponent from food when beneficial
        3. Use flood fill to detect trapped positions
        4. Aggressive positioning and head-on avoidance
        5. Grow strategically and control the board

        Available data:
            self.game_state     - Full game state (see README for format)
            self.player_id      - Your player number (1 or 2)
            self.grid_width     - Width of the game board
            self.grid_height    - Height of the game board
        """
        if not self.game_state:
            return None

        snakes = self.game_state.get("snakes", {})
        my_snake = snakes.get(str(self.player_id))

        if not my_snake or not my_snake.get("body"):
            return None

        head = my_snake["body"][0]
        my_length = len(my_snake["body"])
        current_dir = my_snake.get("direction", "right")

        # Get opponent snake
        opponent_id = str(3 - int(self.player_id))  # If player 1, opponent is 2, vice versa
        opponent_snake = snakes.get(opponent_id)
        opponent_head = opponent_snake["body"][0] if opponent_snake else None
        opponent_length = len(opponent_snake["body"]) if opponent_snake else 0

        foods = self.game_state.get("foods", [])

        # Build dangerous positions (occupied by snake bodies, excluding tails)
        dangerous = set()
        for snake_data in snakes.values():
            body = snake_data.get("body", [])
            for segment in body[:-1]:
                dangerous.add((segment[0], segment[1]))

        # Direction vectors
        directions = {
            "up": (0, -1),
            "down": (0, 1),
            "left": (-1, 0),
            "right": (1, 0)
        }

        opposites = {"up": "down", "down": "up", "left": "right", "right": "left"}

        def is_safe(x, y):
            """Check if position is safe."""
            if x < 0 or x >= self.grid_width or y < 0 or y >= self.grid_height:
                return False
            return (x, y) not in dangerous

        def flood_fill_size(x, y, exclude_pos=None):
            """Use flood fill to count reachable safe spaces from position."""
            visited = set()
            queue = [(x, y)]
            visited.add((x, y))
            
            if not is_safe(x, y):
                return 0
            
            while queue and len(visited) < 100:  # Limit to avoid slowness
                cx, cy = queue.pop(0)
                for dx, dy in directions.values():
                    nx, ny = cx + dx, cy + dy
                    if (nx, ny) not in visited and is_safe(nx, ny):
                        visited.add((nx, ny))
                        queue.append((nx, ny))
            
            return len(visited)

        # Find all safe moves
        safe_moves = []
        for direction, (dx, dy) in directions.items():
            if direction == opposites.get(current_dir):
                continue
            new_x = head[0] + dx
            new_y = head[1] + dy
            if is_safe(new_x, new_y):
                safe_moves.append({"direction": direction, "x": new_x, "y": new_y})

        # If no safe moves, take any non-reversing move to delay death
        if not safe_moves:
            for direction in directions:
                if direction != opposites.get(current_dir):
                    return direction
            return current_dir

        # Score each move
        best_dir = None
        best_score = float('-inf')

        for move in safe_moves:
            score = 0
            new_x, new_y = move["x"], move["y"]

            # Priority 1: CAPTURE FOOD (massive bonus)
            food_on_tile = False
            for food in foods:
                if new_x == food["x"] and new_y == food["y"]:
                    score += 5000
                    food_on_tile = True
                    break

            # Priority 2: FIND NEAREST REACHABLE FOOD
            if not food_on_tile and foods:
                min_food_dist = float('inf')
                for food in foods:
                    dist = abs(new_x - food["x"]) + abs(new_y - food["y"])
                    if dist < min_food_dist:
                        min_food_dist = dist
                
                # Strong incentive to move toward food
                score += max(0, (50 - min_food_dist) * 100)

            # Priority 3: SAFETY - Flood fill to detect traps
            reachable = flood_fill_size(new_x, new_y)
            score += reachable * 30  # Large penalty for moves into tight spaces

            # Priority 4: OPPONENT BLOCKING (if stronger, block them)
            if opponent_head and my_length >= opponent_length - 1:
                opponent_dist = abs(new_x - opponent_head[0]) + abs(new_y - opponent_head[1])
                if opponent_dist < 6:  # Keep pressure when close
                    score += (6 - opponent_dist) * 50

            # Priority 5: AVOID HEAD-ON COLLISION
            if opponent_head:
                if new_x == opponent_head[0] and new_y == opponent_head[1]:
                    score -= 5000  # Never move into opponent's head

            # Priority 6: CENTER CONTROL (small bonus for mid-board positioning)
            center_x, center_y = self.grid_width // 2, self.grid_height // 2
            center_dist = abs(new_x - center_x) + abs(new_y - center_y)
            if my_length > opponent_length:
                score += (30 - center_dist) * 20  # Control center when winning

            # Priority 7: EDGE AVOIDANCE (slight penalty)
            edge_dist = min(new_x, self.grid_width - 1 - new_x,
                           new_y, self.grid_height - 1 - new_y)
            if edge_dist <= 1:
                score -= 200

            if score > best_score:
                best_score = score
                best_dir = move["direction"]

        return best_dir


# ============================================================================
#  MAIN - Parse command line arguments and start the bot
# ============================================================================

async def main():
    parser = argparse.ArgumentParser(description="CopperHead Bot")
    parser.add_argument("--server", "-s", default=GAME_SERVER,
                        help=f"Server WebSocket URL (default: {GAME_SERVER})")
    parser.add_argument("--name", "-n", default=None,
                        help=f"Bot display name (default: {BOT_NAME})")
    parser.add_argument("--difficulty", "-d", type=int, default=5,
                        help="AI difficulty level 1-10 (accepted for compatibility, not yet used)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress console output")
    args = parser.parse_args()

    bot = MyBot(args.server, name=args.name)

    print(f"{bot.name} v{BOT_VERSION}")
    print(f"  Server: {args.server}")
    print()

    await bot.play()


if __name__ == "__main__":
    asyncio.run(main())
