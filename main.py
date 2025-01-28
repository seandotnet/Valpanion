import sys
import base64
import tempfile
from io import BytesIO
from PIL import Image
import os
import webbrowser
import json
import logging
import time
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, 
                             QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QSizePolicy,
                             QStyledItemDelegate, QStyle, QCheckBox, QMessageBox)
from PyQt6.QtGui import QFont, QIcon, QColor, QPainter, QPixmap
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize, QPoint
from valclient.client import Client
import requests
import urllib.parse
from pathlib import Path
import re

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

REGION_ENDPOINTS = {
    'EU': 'https://eu.api.riotgames.com',
    'NA': 'https://na.api.riotgames.com',
    'AP': 'https://ap.api.riotgames.com',
    'KR': 'https://kr.api.riotgames.com'
}

AGENT_NAMES = {
    "569fdd95-4d10-43ab-ca70-79becc718b46": "Sage",
    "a3bfb853-43b2-7238-a4f1-ad90e9e46bcc": "Reyna",
    "95b78ed7-4637-86d9-7e41-71ba8c293152": "Harbor",
    "f94c3b30-42be-e959-889c-5aa313dba261": "Raze",
    "e370fa57-4757-3604-3648-499e1f642d3f": "Gekko",
    "5f8d3a7f-467b-97f3-062c-13acf203c006": "Breach",
    "6f2a04ca-43e0-be17-7f36-b3908627744d": "Skye",
    "117ed9e3-49f3-6512-3ccf-0cada7e3823b": "Cypher",
    "add6443a-41bd-e414-f6ad-e58d267f4e95": "Jett",
    "320b2a48-4d9b-a075-30f1-1f93a9b638fa": "Sova",
    "eb93336a-449b-9c1b-0a54-a891f7921d69": "Phoenix",
    "41fb69c1-4189-7b37-f117-bcaf1e96f1bf": "Astra",
    "707eab51-4836-f488-046a-cda6bf494859": "Viper",
    "dade69b4-4f5a-8528-247b-219e5a1facd6": "Fade",
    "cc8b64c8-4b25-4ff9-6e7f-37b4da43d235": "Deadlock",
    "9f0d8ba9-4140-b941-57d3-a7ad57c6b417": "Brimstone",
    "7f94d92c-4234-0a36-9646-3a87eb8b5c89": "Yoru",
    "601dbbe7-43ce-be57-2a40-4abd24953621": "KAY/O",
    "1e58de9c-4950-5125-93e9-a0aee9f98746": "Killjoy",
    "bb2a4828-46eb-8cd1-e765-15848195d751": "Neon",
    "22697a3d-45bf-8dd7-4fec-84a9e28c69d7": "Chamber",
    "0e38b510-41a8-5780-5e8f-568b2a4f2d6c": "Iso",
    "8e253930-4c05-31dd-1b6c-968525494517": "Omen",
    "1dbf2edd-4729-0984-3115-daa5eed44993": "Clove",
    "efba5359-4016-a1e5-7626-b1ae76895940": "Vyse",
    "b444168c-4e35-8076-db47-ef9bf368f384": "Tejo"
}

def capitalize_first_letter(s):
    return s[0].upper() + s[1:] if s else s


def RankToTier(rank):
    tiers = [
        "Unranked", "Unused1", "Unused2", "Iron 1", "Iron 2", "Iron 3",
        "Bronze 1", "Bronze 2", "Bronze 3", "Silver 1", "Silver 2", "Silver 3",
        "Gold 1", "Gold 2", "Gold 3", "Platinum 1", "Platinum 2", "Platinum 3",
        "Diamond 1", "Diamond 2", "Diamond 3", "Ascendant 1", "Ascendant 2", "Ascendant 3",
        "Immortal 1", "Immortal 2", "Immortal 3", "Radiant"
    ]
    return tiers[rank] if 0 <= rank < len(tiers) else "Unknown"

class StarDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super(StarDelegate, self).__init__(parent)
        self.star_icon = QIcon("path/to/star_icon.png")  # Replace with path to a star icon image

    def paint(self, painter, option, index):
        super(StarDelegate, self).paint(painter, option, index)
        if index.data(Qt.ItemDataRole.UserRole):
            self.star_icon.paint(painter, option.rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def sizeHint(self, option, index):
        size = super(StarDelegate, self).sizeHint(option, index)
        return QSize(size.width() + 25, size.height())

class WorkerThread(QThread):
    resultReady = pyqtSignal(list)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        result = self.func(*self.args, **self.kwargs)
        self.resultReady.emit(result)

class ValorantApp(QMainWindow):
    def __init__(self):
        super().__init__()
        # Add debugging for icon path
        self.icon_path = "assets/icon.ico"
        logging.info(f"Attempting to load icon from: {os.path.abspath(self.icon_path)}")
        
        if not os.path.exists(self.icon_path):
            logging.error(f"Icon file not found at: {os.path.abspath(self.icon_path)}")
        else:
            logging.info("Icon file exists")
            
        # Test if icon can be loaded
        icon = QIcon(self.icon_path)
        if icon.isNull():
            logging.error("Icon failed to load into QIcon")
        else:
            logging.info("Icon successfully loaded into QIcon")
            
        self.client = None
        self.lock_timer = None
        self.countdown_timer = None
        self.countdown_seconds = 5
        self.favorites_file = Path.home() / ".valpanion_favorites.json"
        self.favorites = self.load_favorites()
        self.map_names = {
            "/Game/Maps/Ascent/Ascent": "Ascent",
            "/Game/Maps/Bonsai/Bonsai": "Split",
            "/Game/Maps/Canyon/Canyon": "Fracture",
            "/Game/Maps/Duality/Duality": "Bind",
            "/Game/Maps/Foxtrot/Foxtrot": "Breeze",
            "/Game/Maps/Port/Port": "Icebox",
            "/Game/Maps/Triad/Triad": "Haven",
            "/Game/Maps/Pitt/Pitt": "Pearl",
            "/Game/Maps/Jam/Jam": "Lotus",
            "/Game/Maps/Juliett/Juliett": "Sunset",
            "/Game/Maps/Infinity/Infinity": "Abyss"
        }
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Valpanion (⌐■_■) /git/seandotnet')
        self.setGeometry(100, 100, 1200, 600)
        
        # Set icon with additional checks
        icon = QIcon(self.icon_path)
        if not icon.isNull():
            self.setWindowIcon(icon)
            logging.info("Window icon set successfully")
        else:
            logging.error("Failed to set window icon - icon is null")
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout()

        # Top row: Region and Agent selection
        top_row_layout = QHBoxLayout()
        
        # Region selection (centered)
        region_layout = QHBoxLayout()
        region_label = QLabel("Region:")
        region_label.setFont(QFont('Arial', 12))
        self.region_combo = QComboBox()
        self.region_combo.setFont(QFont('Arial', 12))
        self.region_combo.addItems(['EU', 'NA', 'AP', 'KR'])
        self.region_combo.setFixedHeight(int(self.region_combo.sizeHint().height() * 1.5))
        self.switch_button = QPushButton("Switch")
        self.switch_button.clicked.connect(self.switch_region)
        region_layout.addStretch()
        region_layout.addWidget(region_label)
        region_layout.addWidget(self.region_combo)
        region_layout.addWidget(self.switch_button)
        region_layout.addStretch()
        region_layout.setSpacing(10)
        
        layout.addLayout(region_layout)
        
        # Agent selection and favoriting (centered layout)
        agent_layout = QHBoxLayout()
        
        agent_label = QLabel("Agent to Lock:")
        agent_label.setFont(QFont('Arial', 12))
        
        self.favorite_button = QPushButton("★")
        self.favorite_button.setFixedSize(30, 30)
        self.favorite_button.clicked.connect(self.toggle_favorite)
        
        self.agent_combo = QComboBox()
        self.agent_combo.setFont(QFont('Arial', 12))
        self.agent_combo.setFixedHeight(int(self.agent_combo.sizeHint().height() * 1.5))
        self.agent_combo.setFixedWidth(200)
        
        # Move checkbox here and remove its text
        self.use_favorites_checkbox = QCheckBox()
        self.use_favorites_checkbox.setFont(QFont('Arial', 12))
        
        favorites_label = QLabel("Use Favourites:")
        favorites_label.setFont(QFont('Arial', 12))
        
        self.favorites_combo = QComboBox()
        self.favorites_combo.setFont(QFont('Arial', 12))
        self.favorites_combo.setFixedHeight(int(self.favorites_combo.sizeHint().height() * 1.5))
        self.favorites_combo.setFixedWidth(200)
        
        # Add stretching element to the left
        agent_layout.addStretch()
        
        agent_layout.addWidget(agent_label)
        agent_layout.addWidget(self.favorite_button)
        agent_layout.addWidget(self.agent_combo)
        agent_layout.addSpacing(20)  # Add some space between the two sections
        agent_layout.addWidget(self.use_favorites_checkbox)  # Moved here
        agent_layout.addWidget(favorites_label)
        agent_layout.addWidget(self.favorites_combo)
        
        # Add stretching element to the right
        agent_layout.addStretch()
        
        layout.addLayout(agent_layout)

        # Now that all UI elements are created, we can populate them
        self.populate_agent_combo()
        self.populate_favorites_combo()
        self.agent_combo.currentIndexChanged.connect(self.on_agent_combo_changed)

        # Lock button layout (remove the checkbox from here)
        lock_layout = QHBoxLayout()

        # Create lock button first
        self.lock_button = QPushButton("Lock")
        self.lock_button.setFont(QFont('Arial', 12))
        self.lock_button.setStyleSheet("background-color: darkred; color: white;")
        self.lock_button.setEnabled(False)
        self.lock_button.clicked.connect(self.lock_agent)
        self.lock_button.setFixedSize(int(self.lock_button.sizeHint().width() * 1.5), 
                                   int(self.lock_button.sizeHint().height() * 1.5))

        # Create dodge button after lock button exists
        self.dodge_button = QPushButton("Dodge")
        self.dodge_button.setFont(QFont('Arial', 12))
        self.dodge_button.setStyleSheet("background-color: darkred; color: white;")
        self.dodge_button.setFixedSize(int(self.lock_button.sizeHint().width() * 1.2), 
                                    int(self.lock_button.sizeHint().height() * 1.2))
        self.dodge_button.clicked.connect(self.dodge_game)

        # Add buttons to layout with spacing
        lock_layout.addStretch()
        lock_layout.addWidget(self.dodge_button)
        lock_layout.addSpacing(10)  # Add some space between buttons
        lock_layout.addWidget(self.lock_button)
        lock_layout.addStretch()
        lock_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(lock_layout)

        # Countdown label
        self.countdown_label = QLabel("")
        self.countdown_label.setFont(QFont('Arial', 12))
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.setStyleSheet("color: orange; font-weight: bold;")
        layout.addWidget(self.countdown_label)

        # Game state label
        self.game_state_label = QLabel("Game State: Unknown")
        self.game_state_label.setFont(QFont('Arial', 12))
        self.game_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.game_state_label.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(self.game_state_label)

        # Map and Team info layout
        map_team_layout = QHBoxLayout()

        # Map label
        self.map_label = QLabel("")
        self.map_label.setFont(QFont('Arial', 12))
        self.map_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.map_label.setStyleSheet("color: white; font-weight: bold;")
        map_team_layout.addWidget(self.map_label)

        # Team label
        self.team_label = QLabel("")
        self.team_label.setFont(QFont('Arial', 12))
        self.team_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.team_label.setStyleSheet("font-weight: bold;")
        map_team_layout.addWidget(self.team_label)

        layout.addLayout(map_team_layout)

# Scoreboard table
        self.scoreboard = QTableWidget()
        self.scoreboard.setColumnCount(6)
        self.scoreboard.setHorizontalHeaderLabels(['Team', 'Agent', 'Name', 'Rank', 'RR', 'Tracker'])
        self.scoreboard.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.scoreboard.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.scoreboard.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        layout.addWidget(self.scoreboard)

        # Create and position the Re-fetch button at the bottom right
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()  # This pushes the button to the right
        self.hidden_names_button = QPushButton('Re-fetch Player Details')
        self.hidden_names_button.setFont(QFont('Arial', 12))
        self.hidden_names_button.clicked.connect(self.get_hidden_names)
        self.hidden_names_button.setFixedSize(int(self.hidden_names_button.sizeHint().width() * 1.2), 
                                            int(self.hidden_names_button.sizeHint().height() * 1.2))
        bottom_layout.addWidget(self.hidden_names_button)
        layout.addLayout(bottom_layout)

        central_widget.setLayout(layout)

        # Set up timer for updating game state
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_game_state)
        self.timer.start(1000)  # Update every 1 second

        self.update_favorite_button()

        # Initialize client
        self.initialize_client()

        # Add tracker.gg API headers
        self.tracker_headers = {
            "Host": "api.tracker.network",
            "Connection": "keep-alive",
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": "https://www.overwolf.com/ipmlnnogholfmdmenfijjifldcpjoecappfccceh",
            "TRN-API-Key": "319e5540-bd60-4f5a-9660-6858c9a01350",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OverwolfClient/0.251.2.1",
            "sec-ch-ua": "\"Not_A Brand\";v=\"8\", \"Chromium\";v=\"120\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9"
        }

        # Add this one line to your existing init
        self.flag_cache = {}

    def initialize_client(self):
        try:
            region = self.region_combo.currentText().lower()
            self.client = Client(region=region)
            self.client.activate()
            print(f"Client initialized with region: {region}")
        except Exception as e:
            print(f"Failed to initialize client: {e}")
            self.game_state_label.setText(f"Error: {str(e)}")

    def switch_region(self):
        # Stop the current timer
        self.timer.stop()

        # Reinitialize the client with the new region
        self.initialize_client()

        # Restart the timer
        self.timer.start(1000)

        print(f"Switched to region: {self.region_combo.currentText()}")

    def populate_agent_combo(self):
        self.agent_combo.clear()
        sorted_agents = sorted(AGENT_NAMES.values())
        for agent in sorted_agents:
            self.agent_combo.addItem(agent)
        if self.agent_combo.count() > 0:
            self.update_favorite_button()

    def populate_favorites_combo(self):
        self.favorites_combo.clear()
        for agent in self.favorites:
            self.favorites_combo.addItem(agent)

    def toggle_favorite(self):
        try:
            current_agent = self.agent_combo.currentText()
            if current_agent in self.favorites:
                self.favorites.remove(current_agent)
                logging.info(f"Removed {current_agent} from favorites")
            else:
                self.favorites.append(current_agent)
                logging.info(f"Added {current_agent} to favorites")
            
            self.save_favorites()
            self.populate_favorites_combo()
            self.update_favorite_button()
            logging.info("Favorites updated successfully")
        except Exception as e:
            logging.error(f"Error in toggle_favorite: {e}")
            # Optionally, you can show an error message to the user
            QMessageBox.critical(self, "Error", f"Failed to update favorites: {str(e)}")

    def save_favorites(self):
        try:
            with open(self.favorites_file, 'w') as f:
                json.dump(self.favorites, f)
            logging.info(f"Favorites saved to: {self.favorites_file}")
        except Exception as e:
            logging.error(f"Error saving favorites: {e}")
            raise  # Re-raise the exception to be caught in toggle_favorite

    def update_favorite_button(self):
        if self.agent_combo.count() > 0:
            current_agent = self.agent_combo.currentText()
            if current_agent in self.favorites:
                self.favorite_button.setStyleSheet("background-color: gold;")
            else:
                self.favorite_button.setStyleSheet("")

    def on_agent_combo_changed(self):
        self.update_favorite_button()

    def on_agent_clicked(self, index):
        if index.row() == 0 or index.row() == (len(self.favorites) + 2):  # Skip header items
            return
        
        agent = self.agent_combo.itemText(index.row()).replace("★ ", "")
        if agent in self.favorites:
            self.favorites.remove(agent)
        else:
            self.favorites.append(agent)
        self.save_favorites()
        self.populate_agent_combo()

    def load_favorites(self):
        try:
            if self.favorites_file.exists():
                with open(self.favorites_file, 'r') as f:
                    favorites = json.load(f)
                logging.info(f"Favorites loaded from: {self.favorites_file}")
                return favorites
            else:
                logging.info(f"Favorites file not found at: {self.favorites_file}")
                return []
        except Exception as e:
            logging.error(f"Error loading favorites: {e}")
            return []

    def lock_agent(self):
        if not self.client:
            self.initialize_client()
        try:
            if self.use_favorites_checkbox.isChecked() and self.favorites_combo.count() > 0:
                preferred_agent = self.favorites_combo.currentText()
            else:
                preferred_agent = self.agent_combo.currentText()
            
            agent_id = next(key for key, value in AGENT_NAMES.items() if value == preferred_agent)
            
            match = self.client.pregame_fetch_match()
            self.client.pregame_select_character(agent_id)
            self.client.pregame_lock_character(agent_id)
            
            self.game_state_label.setText(f"Locked {preferred_agent}")
        except Exception as e:
            logging.error(f"Error locking agent: {e}")
            self.game_state_label.setText(f"Error locking agent: {str(e)}")

    def get_hidden_names(self):
        self.hidden_names_button.setEnabled(False)
        self.worker = WorkerThread(self._get_hidden_names, self.region_combo.currentText())
        self.worker.resultReady.connect(self.on_result_ready)
        self.worker.finished.connect(lambda: self.hidden_names_button.setEnabled(True))
        self.worker.start()

    def _get_hidden_names(self, region):
        if not self.client:
            self.initialize_client()
        try:
            logging.debug("Fetching presence...")
            sessionState = self.client.fetch_presence(self.client.puuid)
            if not sessionState:
                return [{"error": "You are not running Valorant or the game is not in the correct state"}]

            sessionState = sessionState['sessionLoopState']
            formatted_players = []

            if sessionState == "INGAME":
                logging.debug("Fetching in-game match data...")
                matchId = self.client.coregame_fetch_player()['MatchID']
                currentMatch = self.client.coregame_fetch_match(matchId)
                players = currentMatch['Players']
                
                # Add these debug logs
                logging.debug(f"Total players in match data: {len(players)}")
                logging.debug("Player IDs in match:")
                for player in players:
                    logging.debug(f"Player ID: {player['Subject']}, Team: {player['TeamID']}, Agent: {player.get('CharacterID', 'Unknown')}")
            elif sessionState == "PREGAME":
                logging.debug("Fetching pre-game match data...")
                pregame_match = self.client.pregame_fetch_match()
                if 'AllyTeam' in pregame_match:
                    players = pregame_match['AllyTeam']['Players']  # This only gets your team
                else:
                    return [{"error": "No players found in pregame"}]
            else:
                return [{"error": f"Unexpected game state: {sessionState}"}]

            # First pass: Get match histories for all players
            player_matches = {}
            for player in players:
                playerID = player['Subject']
                try:
                    match_history = self.client.fetch_match_history(playerID)
                    player_matches[playerID] = set(match['MatchID'] for match in match_history.get('History', [])[:5])
                    logging.debug(f"Got {len(player_matches[playerID])} recent matches for {playerID}")
                except Exception as e:
                    logging.error(f"Error fetching match history for {playerID}: {e}")
                    player_matches[playerID] = set()

            # Process each player
            for player in players:
                playerID = player['Subject']
                try:
                    # Get basic player info
                    player_info = self.client.put(
                        endpoint="/name-service/v2/players",
                        endpoint_type="pd",
                        json_data=[playerID]
                    )[0]

                    # Get player MMR data with improved error handling
                    playerMMR = self.client.fetch_mmr(playerID)
                    currentRank = 0
                    currentRR = 0
                    
                    if playerMMR and "QueueSkills" in playerMMR:
                        comp_data = playerMMR["QueueSkills"].get("competitive", {})
                        if comp_data is None:  # Handle players who never played competitive
                            logging.debug(f"Player {playerID} has no competitive data")
                            currentRank = 0  # Unranked
                            currentRR = 0
                        else:
                            seasonal_info = comp_data.get("SeasonalInfoBySeasonID", {})
                            
                            # Get the current season ID from content
                            seasonContent = self.client.fetch_content()
                            currentAct = None
                            for season in seasonContent['Seasons']:
                                if season['IsActive'] and season['Type'] == "act":
                                    currentAct = season
                                    break
                            
                            if currentAct and currentAct['ID'] in seasonal_info:
                                season_data = seasonal_info[currentAct['ID']]
                                currentRank = season_data.get("CompetitiveTier", 0)
                                currentRR = season_data.get("RankedRating", 0)
                                logging.debug(f"Found rank data: Tier={currentRank}, RR={currentRR} for season {currentAct['ID']}")
                            else:
                                logging.warning(f"No rank data found for current season")
                                currentRank = 0
                                currentRR = 0
                    else:
                        logging.warning(f"No rank data found for player {playerID}")
                        currentRank = 0
                        currentRR = 0

                    # Find potential party members (keeping your existing party detection)
                    party_members = []
                    player_recent_matches = player_matches.get(playerID, set())
                    for other_id, other_matches in player_matches.items():
                        if other_id != playerID:
                            common_matches = player_recent_matches.intersection(other_matches)
                            if len(common_matches) >= 2:  # If they played 2+ games together recently
                                party_members.append(other_id)
                    
                    party_size = len(party_members) + 1 if party_members else 1
                    logging.debug(f"Found party size {party_size} for {playerID} with members {party_members}")

                    # Handle team assignment based on game state
                    if sessionState == "PREGAME":
                        team = "Team"
                    else:  # INGAME
                        team = "Defender" if player.get('TeamID') == 'Blue' else "Attacker"
                    
                    agent = AGENT_NAMES.get(player['CharacterID'], f"Unknown ({player['CharacterID']})")
                    name = f"{player_info['GameName']}#{player_info['TagLine']}"
                    rank = capitalize_first_letter(RankToTier(currentRank))

                    # Get player name parts for tracker.gg API
                    name_parts = name.split('#')
                    if len(name_parts) == 2:
                        tracker_url = f"https://api.tracker.network/api/v2/valorant/standard/profile/riot/{name_parts[0]}%23{name_parts[1]}"
                        try:
                            headers = self.tracker_headers.copy()
                            headers['Accept-Encoding'] = 'gzip, deflate'
                            
                            response = requests.get(tracker_url, headers=headers)
                            data = response.json()
                            
                            # Get country code
                            country_code = data.get('data', {}).get('userInfo', {}).get('countryCode')
                            
                            # Get K/D
                            kd_ratio = "?"
                            segments = data.get('data', {}).get('segments', [])
                            for segment in segments:
                                stats = segment.get('stats', {})
                                if 'kDRatio' in stats:
                                    kd_ratio = stats['kDRatio'].get('displayValue', '?')
                                    break
                                    
                            logging.debug(f"Found K/D for {name}: {kd_ratio}")
                            
                        except Exception as e:
                            logging.error(f"Error fetching tracker.gg data: {e}")
                            country_code = None
                            kd_ratio = "?"
                    else:
                        country_code = None
                        kd_ratio = "?"

                    # Combine rank and RR
                    if currentRank == 0:
                        rank_with_rr = "Unranked"
                    else:
                        rank_with_rr = f"{rank} {currentRR}RR"

                    # Add the processed player data to formatted_players
                    formatted_players.append({
                        'team': team,
                        'agent': agent,
                        'name': name,
                        'rank': rank_with_rr,
                        'kd': kd_ratio,
                        'party_size': party_size,
                        'party_members': party_members,
                        'country_code': country_code,
                        'tracker': f"{name_parts[0]}%23{name_parts[1]}" if len(name_parts) == 2 else name
                    })

                except Exception as e:
                    logging.error(f"Error processing player {playerID}: {e}")
                    continue  # Skip this player but continue processing others

            logging.debug(f"Number of players processed: {len(formatted_players)}")
            return formatted_players

        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            return [{'error': f"Unexpected error: {str(e)}"}]

    def on_result_ready(self, result):
        self.scoreboard.setRowCount(len(result))
        self.scoreboard.setColumnCount(7)  # Keep all 7 columns
        self.scoreboard.setHorizontalHeaderLabels(['Team', 'Agent', 'Name', 'Rank', 'K/D', 'Party', 'Tracker'])

        for row, player in enumerate(result):
            # Restore proper team color logic
            if player['team'] == 'Defender':
                bg_color = QColor("#3885AB")  # Defender green
            elif player['team'] == 'Attacker':
                bg_color = QColor("#781E1E")  # Attacker red
            else:
                bg_color = QColor("#1C1C1C")  # Default dark
            
            for col, (key, width) in enumerate([
                ('team', 80),
                ('agent', 80),
                ('name', 200),
                ('rank', 120),
                ('kd', 80),
                ('party_size', 80),
                ('tracker', 80)
            ]):
                if key == 'party_size':
                    party_size = player.get('party_size', 0)
                    # New party size display logic
                    if party_size == 1:
                        party_text = "Solo"
                    elif party_size == 2:
                        party_text = "Duo 👥"
                    elif party_size == 3:
                        party_text = "Trio ⚡"
                    elif party_size == 4:
                        party_text = "Quad 🤷"
                    elif party_size == 5:
                        party_text = "5 Stack 🤢"
                    else:
                        party_text = ""
                    item = QTableWidgetItem(party_text)
                elif key == 'tracker':
                    continue  # Skip as handled below
                else:
                    text = str(player[key])
                    item = QTableWidgetItem(text)
                    
                    # Add flag only to the name column
                    if key == 'name' and player.get('country_code'):
                        flag = self.get_flag_image(player['country_code'])
                        if flag:
                            item.setData(Qt.ItemDataRole.DecorationRole, flag)
                
                if key != 'tracker':
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setBackground(bg_color)
                    item.setForeground(QColor('white'))
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.scoreboard.setItem(row, col, item)
                    self.scoreboard.setColumnWidth(col, width)

            # Tracker button
            tracker_button = QPushButton("Tracker")
            tracker_button.clicked.connect(lambda checked, tracker=player['tracker']: self.open_tracker(tracker))
            self.scoreboard.setCellWidget(row, 6, tracker_button)

        # Set specific column widths
        self.scoreboard.setColumnWidth(0, 80)  # Team
        self.scoreboard.setColumnWidth(1, 80)  # Agent
        self.scoreboard.setColumnWidth(2, 200)  # Name (wider for flag)
        self.scoreboard.setColumnWidth(3, 120)  # Rank
        self.scoreboard.setColumnWidth(4, 80)  # K/D
        self.scoreboard.setColumnWidth(5, 80)  # Party
        self.scoreboard.setColumnWidth(6, 80)  # Tracker

        # Set row height to accommodate flags
        for row in range(self.scoreboard.rowCount()):
            self.scoreboard.setRowHeight(row, 30)

    def open_tracker(self, tracker_name):
        try:
            # tracker_name should already be in the format "name%23tag"
            tracker_url = f"https://tracker.gg/valorant/profile/riot/{tracker_name}/overview"
            webbrowser.open(tracker_url)
        except Exception as e:
            logging.error(f"Error opening tracker: {e}")
            QMessageBox.warning(self, "Error", "Failed to open tracker profile")

    def update_game_state(self):
        if not self.client:
            self.game_state_label.setText("Game State: Valorant not running")
            self.map_label.setText("")
            self.team_label.setText("")
            return

        try:
            presence = self.client.fetch_presence(self.client.puuid)
            if presence:
                state = presence['sessionLoopState']
                previous_state = getattr(self, 'previous_state', None)  # Get previous state
                
                # Update state only if it changed
                if state != previous_state:
                    if state == "MENUS":
                        self.game_state_label.setText("Game State: In Menus")
                        self.lock_button.setEnabled(False)
                        self.lock_button.setStyleSheet("background-color: darkred; color: white;")
                        self.countdown_label.setText("")
                        self.map_label.setText("")
                        self.team_label.setText("")
                        self.scoreboard.setRowCount(0)  # Clear the scoreboard
                    elif state == "PREGAME":
                        self.game_state_label.setText("Game State: Pre-Game")
                        if not self.lock_timer and not self.countdown_timer:
                            self.start_lock_countdown()
                        self.update_pregame_info()
                        # Automatically get player details
                        self.get_hidden_names()
                    elif state == "INGAME":
                        self.game_state_label.setText("Game State: In Game")
                        self.lock_button.setEnabled(False)
                        self.lock_button.setStyleSheet("background-color: darkred; color: white;")
                        self.countdown_label.setText("")
                        self.update_map_and_team_info()
                        # Automatically get player details
                        self.get_hidden_names()
                    else:
                        self.game_state_label.setText(f"Game State: {state}")
                        self.map_label.setText("")
                        self.team_label.setText("")
                    
                    # Store current state for next comparison
                    self.previous_state = state
            else:
                self.game_state_label.setText("Game State: Unknown")
                self.map_label.setText("")
                self.team_label.setText("")
        except Exception as e:
            self.game_state_label.setText(f"Game State: Error - {str(e)}")
            self.map_label.setText("")
            self.team_label.setText("")

    def update_pregame_info(self):
        try:
            pregame_info = self.client.pregame_fetch_match()
            
            # Get the map name
            map_id = pregame_info.get('MapID', 'Unknown')
            map_name = self.map_names.get(map_id, map_id.split('/')[-1])
            self.map_label.setText(f"Map - {map_name}")

            # Find the current player in the match data
            current_player = next((player for player in pregame_info['AllyTeam']['Players'] if player['Subject'] == self.client.puuid), None)

            if current_player:
                player_team = pregame_info['AllyTeam']['TeamID']
                if player_team == "Blue":
                    self.team_label.setText("Team: Defender")
                    self.team_label.setStyleSheet("color: #3376b5; font-weight: bold;")
                elif player_team == "Red":
                    self.team_label.setText("Team: Attacker")
                    self.team_label.setStyleSheet("color: #b53333; font-weight: bold;")
                else:
                    self.team_label.setText(f"Team: Unknown ({player_team})")
                    self.team_label.setStyleSheet("color: gray; font-weight: bold;")
            else:
                self.team_label.setText("Team: Player not found in match")
                self.team_label.setStyleSheet("color: orange; font-weight: bold;")
        except Exception as e:
            self.map_label.setText("Map: Error")
            self.team_label.setText(f"Team: Error - {str(e)}")
            self.team_label.setStyleSheet("color: red; font-weight: bold;")

    def update_map_and_team_info(self):
        try:
            # First, fetch the current match ID
            match_data = self.client.coregame_fetch_player()
            match_id = match_data['MatchID']

            # Then, fetch the full match data
            full_match_data = self.client.coregame_fetch_match(match_id)

            # Get the map name
            map_id = full_match_data.get('MapID', 'Unknown')
            map_name = self.map_names.get(map_id, map_id.split('/')[-1])
            self.map_label.setText(f"Map - {map_name}")

            # Find the current player in the match data
            current_player = next((player for player in full_match_data['Players'] if player['Subject'] == self.client.puuid), None)

            if current_player:
                player_team = current_player['TeamID']
                if player_team == "Blue":
                    self.team_label.setText("Team: Defender")
                    self.team_label.setStyleSheet("color: #3376b5; font-weight: bold;")
                elif player_team == "Red":
                    self.team_label.setText("Team: Attacker")
                    self.team_label.setStyleSheet("color: #b53333; font-weight: bold;")
                else:
                    self.team_label.setText(f"Team: Unknown ({player_team})")
                    self.team_label.setStyleSheet("color: gray; font-weight: bold;")
            else:
                self.team_label.setText("Team: Player not found in match")
                self.team_label.setStyleSheet("color: orange; font-weight: bold;")
        except Exception as e:
            self.map_label.setText("Map: Error")
            self.team_label.setText(f"Team: Error - {str(e)}")
            self.team_label.setStyleSheet("color: red; font-weight: bold;")

    def start_lock_countdown(self):
        self.countdown_seconds = 5
        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self.update_countdown)
        self.countdown_timer.start(1000)  # 1 second interval
        self.update_countdown()  # Call immediately to show initial countdown
    
    def update_countdown(self):
        if self.countdown_seconds > 0:
            self.countdown_label.setText(f"I don't want API ban so waiting {self.countdown_seconds} seconds to lock agent :3")
            self.countdown_seconds -= 1
        else:
            self.countdown_timer.stop()
            self.countdown_label.setText("")
            self.enable_lock_button()

    def enable_lock_button(self):
        self.lock_button.setEnabled(True)
        self.lock_button.setStyleSheet("background-color: red; color: white;")
        if self.lock_timer:
            self.lock_timer.stop()
            self.lock_timer = None

    def closeEvent(self, event):
        # Remove the icon file deletion since we're using a permanent file now
        super().closeEvent(event)

    def dodge_game(self):
        """Handles dodging the current game"""
        try:
            # Call VALORANT API to dodge current match
            self.client.pregame_quit_match()
            self.game_state_label.setText("Successfully dodged match")
        except Exception as e:
            self.game_state_label.setText(f"Failed to dodge match: {str(e)}")
            logging.error(f"Error dodging: {e}")

    # Add this new method
    def get_flag_image(self, country_code):
        if not country_code:
            return None
            
        if country_code in self.flag_cache:
            return self.flag_cache[country_code]
            
        url = f"https://flagcdn.com/w20/{country_code.lower()}.png"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                pixmap = QPixmap()
                pixmap.loadFromData(response.content)
                pixmap = pixmap.scaledToHeight(15)
                self.flag_cache[country_code] = pixmap
                return pixmap
        except Exception as e:
            logging.error(f"Error loading flag for {country_code}: {e}")
        return None

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = ValorantApp()
    ex.show()
    sys.exit(app.exec())

