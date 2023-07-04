import os
import sys
import io
import csv
import folium
import json
import sqlite3
from selenium import webdriver
from multiprocessing import Process, Queue
from loginUI import *
from http.server import BaseHTTPRequestHandler, HTTPServer
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5 import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from home import Ui_MainWindow
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg,
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
import matplotlib
import matplotlib.pyplot as plt
matplotlib.use("Qt5Agg")
import pyrebase
import threading
import datetime
import geopy.distance
import smtplib
import ssl
from email.message import EmailMessage


firebaseConfig = {
    "apiKey": "AIzaSyCcJvWUMsUggTU6AtDepoyArvL2MANKyoo",
    "authDomain": "rtos-62f4e.firebaseapp.com",
    "databaseURL": "https://rtos-62f4e-default-rtdb.asia-southeast1.firebasedatabase.app",
    "projectId": "rtos-62f4e",
    "storageBucket": "rtos-62f4e.appspot.com",
    "messagingSenderId": "724293303430",
    "appId": "1:724293303430:web:a3d494c83d05173164a507",
    "measurementId": "G-B3CP485111",
}
firebase = pyrebase.initialize_app(firebaseConfig)
db = firebase.database()

coords = []
forward = 1
time = ""
search_time = ""
temp_threshold = 35
humid_threshold = 50

################################################
############# MAIN WINDOWS CLASS ###############
################################################


def find_popup_slice(html):
    """
    Find the starting and edning index of popup function
    """

    pattern = "function latLngPop(e)"

    # startinf index
    starting_index = html.find(pattern)

    #
    tmp_html = html[starting_index:]

    #
    found = 0
    index = 0
    opening_found = False
    while not opening_found or found > 0:
        if tmp_html[index] == "{":
            found += 1
            opening_found = True
        elif tmp_html[index] == "}":
            found -= 1

        index += 1

    # determine the edning index of popup function
    ending_index = starting_index + index

    return starting_index, ending_index


def find_variable_name(html, name_start):
    variable_pattern = "var "
    pattern = variable_pattern + name_start

    starting_index = html.find(pattern) + len(variable_pattern)
    tmp_html = html[starting_index:]
    ending_index = tmp_html.find(" =") + starting_index

    return html[starting_index:ending_index]


def custom_code(popup_variable_name, map_variable_name, folium_port):
    return """
            // custom code
            function latLngPop(e) {
                %s
                    .setLatLng(e.latlng)
                    .setContent(`
                        lat: ${e.latlng.lat}, lng: ${e.latlng.lng}
                        <button onClick="
                            fetch('http://localhost:%s', {
                                method: 'POST',
                                mode: 'no-cors',
                                headers: {
                                    'Accept': 'application/json',
                                    'Content-Type': 'application/json'
                                },
                                body: JSON.stringify({
                                    latitude: ${e.latlng.lat},
                                    longitude: ${e.latlng.lng}
                                })
                            });
                            L.marker(
                                [${e.latlng.lat}, ${e.latlng.lng}],
                                {}
                            ).addTo(%s);
                        "> Store Coordinate </button>
                        <button onClick="
                            fetch('http://localhost:%s', {
                                method: 'POST',
                                mode: 'no-cors',
                                headers: {
                                    'Accept': 'application/json',
                                    'Content-Type': 'application/json'
                                },
                                body: 'q'
                            });
                        "> Quit </button>
                    `)
                    .openOn(%s);
            }
            // end custom code
    """ % (
        popup_variable_name,
        folium_port,
        map_variable_name,
        folium_port,
        map_variable_name,
    )


def create_folium_map(map_filepath, center_coord, folium_port):
    # create folium map
    vmap = folium.Map(center_coord, zoom_start=9)

    # add popup
    folium.LatLngPopup().add_to(vmap)

    # store the map to a file
    vmap.save(map_filepath)

    # read ing the folium file
    html = None
    with open(map_filepath, "r") as mapfile:
        html = mapfile.read()

    # find variable names
    map_variable_name = find_variable_name(html, "map_")
    popup_variable_name = find_variable_name(html, "lat_lng_popup_")

    # determine popup function indicies
    pstart, pend = find_popup_slice(html)

    # inject code
    with open(map_filepath, "w") as mapfile:
        mapfile.write(
            html[:pstart]
            + custom_code(popup_variable_name, map_variable_name, folium_port)
            + html[pend:]
        )


def open_folium_map(project_url, map_filepath):
    driver = None
    try:
        driver = webdriver.Chrome()
        driver.get(project_url + map_filepath)
    except Exception as ex:
        print(f"Driver failed to open/find url: {ex}")

    return driver


def close_folium_map(driver):
    try:
        driver.close()
    except Exception as ex:
        pass


class dataCollection:
    def __init__(self, pathdb, pathcsv, db):
        self.infomations = information()
        self.db = db
        self.pathdb = pathdb
        self.pathcsv = pathcsv
        self.create_database()

    def create_database(self):
        conn = sqlite3.connect(self.pathdb + "\\" + self.db + ".db")
        c = conn.cursor()
        try:
            c.execute(
                """CREATE TABLE """
                + self.db
                + """(
                Temperature INTEGER,
                Humidity INTEGER,
                Area INTEGER,
                Time text
                )"""
            )

        except Exception as e:
            print(e)
        conn.commit()
        conn.close()

    def insert_database(self):
        conn = sqlite3.connect(self.pathdb + "\\" + self.db + ".db")
        c = conn.cursor()
        c.execute(
            "INSERT INTO "
            + self.db
            + " VALUES(:Temperature , :Humidity, :Area , :Time )",
            {
                "Temperature": self.infomations.Temperature,
                "Humidity": self.infomations.Humidity,
                "Area": self.infomations.Area,
                "Time": self.infomations.Time,
            },
        )
        conn.commit()
        conn.close()

    def search_database(self, timeStart, timeEnd):
        conn = sqlite3.connect(self.pathdb + "\\" + self.db + ".db")
        c = conn.cursor()
        c.execute(
            "SELECT * FROM " + self.db + " WHERE Time BETWEEN ? AND ?",
            (timeStart, timeEnd),
        )
        rows = c.fetchall()
        conn.commit()
        conn.close()
        return rows
    
    def search_database_area(self, timeStart, timeEnd, area):
        conn = sqlite3.connect(self.pathdb + "\\" + self.db + ".db")
        c = conn.cursor()
        c.execute(
            "SELECT * FROM " + self.db + " WHERE Time BETWEEN ? AND ? AND Area = ?",
            (timeStart, timeEnd, area),
        )
        rows = c.fetchall()
        conn.commit()
        conn.close()
        return rows

    def export_CSV(self):
        conn = sqlite3.connect(self.pathdb + "\\" + self.db + ".db")
        c = conn.cursor()
        c.execute(f"select * from {self.db};")
        with open(f"{self.pathcsv}\{self.db}.csv", 'w',newline='') as csv_file: 
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow([i[0] for i in c.description]) 
            csv_writer.writerows(c)
        conn.close()

class information:
    def __init__(self):
        self.Temperature = 0
        self.Humidity = 0
        self.Area = 0
        self.Time = ""


class FoliumServer(BaseHTTPRequestHandler):
    def _set_response(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers["Content-Length"])
        post_data = self.rfile.read(content_length)

        data = post_data.decode("utf-8")
        print(data)
        if data.lower() == "q":
            raise KeyboardInterrupt("Intended exception to exit webserver")

        coords.append(json.loads(data))

        self._set_response()


def listen_to_folium_map(port=3001):
    server_address = ("", port)
    httpd = HTTPServer(server_address, FoliumServer)
    print("Server started")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass

    httpd.server_close()
    print("Server stopped...")


def runserver():
    global coords
    # create variables
    folium_port = 3001
    # center_coord = []
    map_filepath = "folium-map.html"
    lat = db.child("CAR").child("Latitude").get().val()
    long = db.child("CAR").child("Longitude").get().val()
    center_coord = [lat, long]
    project_url = os.path.dirname(__file__) + "/"
    coordinate_filepath = "coordinates.json"

    # create folium map
    create_folium_map(
        os.path.join(project_url, map_filepath), center_coord, folium_port
    )

    # open the folium map (selenium)
    driver = open_folium_map(project_url, map_filepath)

    # run webserer that listens to sent coordinates
    listen_to_folium_map(port=folium_port)

    # close the folium map
    close_folium_map(driver)

    # print all collected coords
    file_path = os.path.join(project_url, "coordinates.json")
    json.dump(coords, open(file_path, "w"))
    coords = []


class MplCanvas(FigureCanvasQTAgg):
    def __init__(self, parent=None, width=5, height=3, dpi=80):
        plt.style.use("dark_background")

        for param in ["text.color", "axes.labelcolor", "xtick.color", "ytick.color"]:
            plt.rcParams[param] = "0.9"  # very light grey

        for param in ["figure.facecolor", "axes.facecolor", "savefig.facecolor"]:
            plt.rcParams[param] = "#212946"  # bluish dark grey

        colors = [
            "#08F7FE",  # teal/cyan
            "#FE53BB",  # pink
            "#F5D300",  # yellow
            "#00ff41",  # matrix green
        ]

        fig = Figure(figsize=(width, height), dpi=dpi)
        fig.tight_layout()
        self.axes = fig.add_subplot(111)
        super(MplCanvas, self).__init__(fig)


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.anime = False
        file_path = os.path.join(os.path.dirname(__file__), "coordinates.json")
        locations = json.load(open(file_path, "r"))
        coords = locations
        lat = db.child("GPS").child("Latitude").get().val()
        long = db.child("GPS").child("Longitude").get().val()
        self.m = folium.Map(
            location=[lat, long],
            zoom_start=15,
        )
        marker = folium.Marker(
                location=[lat, long],
                icon=folium.Icon(color="purple"),
                popup="CAR POSITION",
            )
        marker.add_to(self.m)
        self.data = io.BytesIO()
        self.m.save(self.data, close_file=False)
        self.location = {}
        self.webView = QWebEngineView()
        self.webView.setHtml(self.data.getvalue().decode())
        file_path = os.path.join(os.path.dirname(__file__), "setting.json")
        settings = json.load(open(file_path, "r"))
        self.pathdb = settings["pathdb"]
        self.pathcsv = settings["pathcsv"]
        self.database = settings["dbname"]
        self.ui.textEdit_4.setPlainText(self.database)
        self.ui.textEdit_5.setPlainText(self.pathdb)
        self.ui.textEdit_6.setPlainText(self.pathcsv)
        self.timer = QtCore.QTimer()
        self.timer2 = QtCore.QTimer()
        self.gps_timer = QTimer()
        self.log_timer = QTimer()
        self.live_timer = QTimer()
        self.x1 = 30 * [0]
        self.x2 = 30 * [0]
        self.y1 = [0] * 30
        self.y2 = [0] * 30
        for i in range(30):
            self.x1[i] = i
            self.x2[i] = i
        self.count = 0
        self.final_waypoint = len(coords)
        self.sc1 = MplCanvas(self, dpi=80)
        self.sc2 = MplCanvas(self, dpi=80)
        self.sc3 = MplCanvas(self, dpi=80)
        self.sc4 = MplCanvas(self, dpi=80)
        self.ui.Humidity_graph.addWidget(self.sc1)
        self.ui.Temperature_graph.addWidget(self.sc2)
        self.ui.verticalLayout_20.addWidget(self.sc3)
        self.ui.verticalLayout_21.addWidget(self.sc4)
        db.child("CAR").update({"ENABLE": "OFF"})
        db.update({"STATUS": "MOVING"})
        
        self.ui.verticalLayout_6.addWidget(self.webView)
        # PAGE 1
        self.ui.CAR_button.clicked.connect(self.set_page1)
        # PAGE 2
        self.ui.GPS_button.clicked.connect(self.set_page2)
        # PAGE 3
        self.ui.DATA_button.clicked.connect(self.set_page3)
        # PAGE 4
        self.ui.PRODUCT_button.clicked.connect(self.set_page4)
        # PAGE 5
        self.ui.SETTING_button.clicked.connect(self.set_page5)
        
        self.ui.checkBox_3.stateChanged.connect(self.draw_line)

        self.ui.checkBox.stateChanged.connect(self.enable_log)
        # SETTING EXITBUTTOM
        self.ui.exit_button.clicked.connect(self.closeEvent)
        # BACK
        self.ui.back_button.clicked.connect(self.test)
        # GPS SEND
        self.ui.pushButton.clicked.connect(self.htmlthread)
        # SEND MESS
        self.ui.pushButton_11.clicked.connect(self.add_table_item)
        # SEND ENABLE
        self.ui.pushButton_12.clicked.connect(self.send_enable)
        # SET TEMP AND HUMID THRESHOLD
        self.ui.pushButton_6.clicked.connect(self.save_threshold)
        # CHANGE TABLE TO GRAPH PAGE 3
        self.ui.pushButton_13.clicked.connect(self.show_graph)
        # ERASE THE GPS COORDS
        self.ui.pushButton_14.clicked.connect(self.clear_coordinates)
        # EXPORT CSV
        self.ui.pushButton_15.clicked.connect(self.export_csvfile)
        # SAVE SETTING CONFIG
        self.ui.pushButton_17.clicked.connect(self.save_setting)
        # SEND EMAIL
        self.ui.pushButton_10.clicked.connect(self.send_email)

        self.my_stream = db.stream(self.stream_handler)
        self.ui.tableWidget.setColumnWidth(0, 150)
        self.ui.tableWidget.setColumnWidth(1, 150)
        self.ui.tableWidget.setColumnWidth(2, 150)
        self.ui.tableWidget.setColumnWidth(3, 300)

        self.timer.timeout.connect(self.timerthread)
        self.timer2.timeout.connect(self.page_thread)
        self.log_timer.timeout.connect(self.log_thread)
        self.live_timer.timeout.connect(self.live_track)
        self.gps_timer.timeout.connect(self.map_update)
        self.activate_timer()

    # ACTIVATE TIMER
    def activate_timer(self):
        self.timer.start(3000)
        self.timer2.start(1000)
        self.log_timer.start(11000)
        self.live_timer.start(11000)

    ################################################
    ################## SLICE 1 #####################
    ################################################
    def set_page1(self):
        if self.gps_timer.isActive():
            self.gps_timer.stop()
        self.ui.stackedWidget.setCurrentWidget(self.ui.page_1)
        self.ui.verticalLayout_6.addWidget(self.webView)
        self.ui.Humidity_graph.addWidget(self.sc1)
        self.ui.Temperature_graph.addWidget(self.sc2)

    ################################################
    ################## SLICE 2 #####################
    ################################################
    def set_page2(self):
        if self.gps_timer.isActive():
            self.gps_timer.stop()
        else:
            self.gps_timer.start(1000)
        self.ui.horizontalLayout_9.addWidget(self.webView)
        self.ui.stackedWidget.setCurrentWidget(self.ui.page_2)
        

    def map_update(self):
        '''
        show the new waypoint on window when the there are new coordinates
        '''
        try:
            file_path = os.path.join(os.path.dirname(__file__), "coordinates.json")
            locations = json.load(open(file_path, "r"))
            self.m = folium.Map(
                location=[locations[0]["latitude"], locations[0]["longitude"]],
                zoom_start=15,
            )
            for location in locations:
                marker = folium.Marker(
                    location=[location["latitude"], location["longitude"]],
                    icon=folium.Icon(color="red"),
                    popup="CAR POSITION",
                )
                marker.add_to(self.m)
            if self.location != locations:
                self.location = locations
                self.data.truncate(0)
                self.data.seek(0)
                self.m.save(self.data, close_file=False)
                self.webView.setHtml(self.data.getvalue().decode())
                print("success")
            else:
                print("fail")
        except Exception as e:
            print(f"Exception error at map_update: {e}")
        self.ui.horizontalLayout_9.addWidget(self.webView)
    ################################################
    ################## SLICE 3 #####################
    ################################################
    def set_page3(self):
        if self.gps_timer.isActive():
            self.gps_timer.stop()
        self.ui.stackedWidget.setCurrentWidget(self.ui.page_3)
        # self.ui.verticalLayout_20.addWidget(self.sc1)
        # self.ui.verticalLayout_21.addWidget(self.sc2)

    ################################################
    ################## SLICE 4 #####################
    ################################################
    def set_page4(self):
        if self.gps_timer.isActive():
            self.gps_timer.stop()
        self.ui.stackedWidget.setCurrentWidget(self.ui.page_4)

    ################################################
    ################## SLICE 5 #####################
    ################################################
    def set_page5(self):
        if self.gps_timer.isActive():
            self.gps_timer.stop()
        self.ui.stackedWidget.setCurrentWidget(self.ui.page_5)


    ###############################################
    ############ EXIT AND BACK BUTTOM #############
    ###############################################
    def stream_handler(self, message):
        # print(message["path"])
        if message["path"] == "/STATUS":
            self.send_gps()
        # if message["path"] == "/ALIVE":
        #     if message["data"] == "YES":
                

    def stream_handler_gps(self, message):
        print(message["path"])

################################################
############ GPS COORDINATE LOG  ###############
################################################

    def send_gps(self):
        global forward
        file_path = os.path.join(os.path.dirname(__file__), "coordinates.json")
        locations = json.load(open(file_path, "r"))
        if self.ui.checkBox_2.isChecked():
            if self.count == self.final_waypoint and forward == 1:
                forward = 0
            elif self.count == 0 and forward == 0:
                forward = 1
            if forward == 1:
                db.child("CAR").update(
                    {"Latitude": str(locations[self.count]["latitude"])}
                )
                db.child("CAR").update(
                    {"Longitude": str(locations[self.count]["longitude"])}
                )
                db.update({"STATUS": "MOVING"})
                self.count += 1
            else:
                self.count -= 1
                db.child("CAR").update(
                    {"Latitude": str(locations[self.count]["latitude"])}
                )
                db.child("CAR").update(
                    {"Longitude": str(locations[self.count]["longitude"])}
                )
                db.update({"STATUS": "MOVING"})
        else:
            if self.count < self.final_waypoint:
                db.child("CAR").update(
                    {"Latitude": str(locations[self.count]["latitude"])}
                )
                db.child("CAR").update(
                    {"Longitude": str(locations[self.count]["longitude"])}
                )
                db.update({"STATUS": "MOVING"})
                self.count += 1
            else:
                db.update({"STATUS": "PAUSE"})
        
        # print(f"final waypoints {self.final_waypoint}")
        # print(f"count {self.count}")
        # print(f"forward {forward}")
    
    def live_track(self):
        global gps_lat
        global gps_long
        current_widget = self.ui.stackedWidget.currentWidget().objectName()
        if current_widget == "page_1" or current_widget == "page_2":
            self.m = folium.Map(
                location=[gps_lat.val(), gps_long.val()],
                zoom_start=15,
            )
            marker = folium.Marker(
                    location=[gps_lat.val(), gps_long.val()],
                    icon=folium.Icon(color="purple"),
                    popup="CAR POSITION",
            )
            marker.add_to(self.m)
            html_content = self.m.get_root().render()
            self.data.seek(0)
            self.data.truncate()
            if self.ui.checkBox.isChecked() == False and self.ui.checkBox_3.isChecked() == False:
                self.data.write(html_content.encode())
                self.webView.setHtml(self.data.getvalue().decode())
                if current_widget == "page_1":
                    self.ui.verticalLayout_6.addWidget(self.webView)
                else:
                    self.ui.horizontalLayout_9.addWidget(self.webView)

    def draw_line(self):
        if self.ui.checkBox_3.isChecked():
            file_path = os.path.join(os.path.dirname(__file__), "gps_log_coordinates.json")
            try:
                with open(file_path, "r") as infile:
                    data = json.load(infile)
                    if data != []: 
                        list_of_lists = [[d[key] for key in d if not isinstance(d[key], str)] for d in data]
                        self.m = folium.Map(
                            location=[data[0]["latitude"], data[0]["longitude"]],
                            zoom_start=15,
                        )
                        folium.PolyLine(locations=list_of_lists, color='blue').add_to(self.m)
            
                file_path = os.path.join(os.path.dirname(__file__), "coordinates.json")
                locations = json.load(open(file_path, "r"))
                if locations != []:
                    for location in locations:
                        marker = folium.Marker(
                            location=[location["latitude"], location["longitude"]],
                            icon=folium.Icon(color="red"),
                            popup="CAR POSITION",
                        )
                        marker.add_to(self.m)
                self.data.truncate(0)
                self.data.seek(0)
                self.m.save(self.data, close_file=False)
                self.webView.setHtml(self.data.getvalue().decode())
                self.ui.horizontalLayout_9.addWidget(self.webView)
            except Exception as e:
                print(e)

    def enable_log(self):
        '''
        toggle checkbox to show both coordinates of car and coordinates of waypoints
        '''
        if self.ui.checkBox.isChecked():
            file_path = os.path.join(
                os.path.dirname(__file__), "gps_log_coordinates.json"
            )
            locations = json.load(open(file_path, "r"))
            if locations != []: 
                self.m = folium.Map(
                    location=[locations[0]["latitude"], locations[0]["longitude"]],
                    zoom_start=15,
                )
                for location in locations:
                    marker = folium.Marker(
                        location=[location["latitude"], location["longitude"]],
                        icon=folium.Icon(color="blue"),
                        popup="CAR POSITION",
                    )
                    marker.add_to(self.m)
            file_path = os.path.join(os.path.dirname(__file__), "coordinates.json")
            locations = json.load(open(file_path, "r"))
            if locations != []:
                for location in locations:
                    marker = folium.Marker(
                        location=[location["latitude"], location["longitude"]],
                        icon=folium.Icon(color="red"),
                        popup="CAR POSITION",
                    )
                    marker.add_to(self.m)
            self.data.truncate(0)
            self.data.seek(0)
            self.m.save(self.data, close_file=False)
            self.webView.setHtml(self.data.getvalue().decode())
            self.ui.horizontalLayout_9.addWidget(self.webView)

    def htmlthread(self):
        self.count = 0
        html_thread = threading.Thread(target=runserver)
        html_thread.start()
        # html_thread.join()

    def test(self):
        if self.anime == False:
            self.anim = QPropertyAnimation(self.ui.frame, b"minimumSize")
            self.anim.setDuration(200)
            self.anim.setStartValue(QtCore.QSize(0, 0))
            self.anim.setEndValue(QtCore.QSize(100, 0))
            self.anim.start()
            self.anime = True
        else:
            self.anim = QPropertyAnimation(self.ui.frame, b"minimumSize")
            self.anim.setDuration(200)
            self.anim.setStartValue(QtCore.QSize(100, 0))
            self.anim.setEndValue(QtCore.QSize(0, 0))
            self.anim.start()
            self.anime = False

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        db.child("CAR").update({"ENABLE": "OFF"})
        return super().closeEvent()

    def log_thread(self):
        gpslog_thread = threading.Thread(target=self.gps_log)
        gpslog_thread.start()

    def gps_log(self):
        '''
        this function get called by timer, every timeout update current gps coordinates to JSON file
        '''
        lat = db.child("GPS").child("Latitude").get().val()
        long = db.child("GPS").child("Longitude").get().val()
        if lat == 0 and long == 0:
            return

        file_path = os.path.join(os.path.dirname(__file__), "gps_log_coordinates.json")

        try:
            if os.path.exists(file_path):
                # if the file exists, read the existing data
                with open(file_path, "r") as infile:
                    data = json.load(infile)
            else:
                # if the file doesn't exist, create an empty list
                data = []

            new_data = {
                "latitude": lat,
                "longitude": long,
                "time": datetime.datetime.now().strftime("%d-%m-%y"),
            }
            data.append(new_data)

            with open(file_path, "w") as outfile:
                json.dump(data, outfile)
                print("File saved successfully!")
        except Exception as e:
            print("Error saving file:", e)
    
    def clear_coordinates(self):
        data = []
        file_path = os.path.join(os.path.dirname(__file__), "gps_log_coordinates.json")
        with open(file_path, "w") as outfile:
            json.dump(data, outfile)


################################################
############ page threading timer  #############
################################################

    def timerthread(self):
        global time
        time = datetime.datetime.now().strftime("%d:%m:%Y %H:%M:%S")
        my_thread1 = threading.Thread(target=self.add_temp)
        my_thread1.start()
        my_thread2 = threading.Thread(target=self.add_humid)
        my_thread2.start()
        my_thread3 = threading.Thread(target=self.add_db)
        my_thread3.start()
        print("thread running")

    def update_variables(self):
        global coords
        global temp
        global humid
        global gps_lat
        global gps_long
        global gps_heading
        global car_lat
        global car_long
        global status
        global time
        temp = db.child("ESP32").child("Temp").get()
        humid = db.child("ESP32").child("Humid").get()
        gps_lat = db.child("GPS").child("Latitude").get()
        gps_long = db.child("GPS").child("Longitude").get()
        gps_heading = db.child("GPS").child("Heading").get()
        status = db.child("STATUS").get()
        car_lat = db.child("CAR").child("Latitude").get()
        car_long = db.child("CAR").child("Longitude").get()


    def page_function(self):
        global time
        global temp
        global humid
        global gps_lat
        global gps_long
        global gps_heading
        global car_lat
        global car_long
        global status
        date = datetime.datetime.now()
        time = date.strftime("%d:%m:%Y %H:%M:%S")
        current_widget = self.ui.stackedWidget.currentWidget()
        if current_widget.objectName() == "page_1":
            try:
                self.ui.label_7.setText(time)
                self.ui.label_8.setText(time)
                self.ui.label_42.setText(str(self.final_waypoint - self.count))
                self.ui.label_40.setText(str(gps_lat.val()) + ", " + str(gps_long.val()))
                self.ui.label_39.setText(status.val())
                self.ui.label_52.setText(str(gps_heading.val()))
                self.ui.label_4.setText(str(humid.val()))
                self.ui.label_5.setText(str(temp.val()))
                self.warning_threshold()
            except Exception as e:
                print(e)
        elif current_widget.objectName() == "page_2":
            try:
                file_path = os.path.join(os.path.dirname(__file__), "coordinates.json")
                data = json.load(open(file_path, "r"))
                self.final_waypoint = len(data)
                self.ui.label_34.setText(str(self.final_waypoint - self.count))
                if self.count == 0:
                    self.ui.label_35.setText(
                        f"{data[self.count]['latitude']:.8f}, {data[self.count]['longitude']:.8f}"
                    )
                else:
                    self.ui.label_35.setText(
                        f"{data[self.count - 1]['latitude']:.8f}, {data[self.count - 1]['longitude']:.8f}"
                    )
                print(self.count)
                self.ui.label_22.setText(str(gps_heading.val()))
                self.ui.label_18.setText(str(gps_lat.val()))
                self.ui.label_16.setText(str(gps_long.val()))
            except Exception as e:
                print(f"Exception error at page_function: {e}")

    def page_thread(self):
        update_thread = threading.Thread(target=self.update_variables)
        update_thread.start()
        function_thread = threading.Thread(target=self.page_function)
        function_thread.start()


################################################
############ temperature and humidity ##########
################################################

    def save_threshold(self):
         global temp_threshold
         global humid_threshold
         temp_threshold = int(self.ui.textEdit_2.toPlainText())
         humid_threshold = int(self.ui.textEdit_3.toPlainText())

    def plot_data_temp(self):
        global temp_threshold
        self.sc1.axes.clear()
        if self.y1[len(self.y1) - 1] > temp_threshold:
            self.sc1.axes.plot(self.x1, self.y1, marker="o", color="#FE5353")
        else:
            self.sc1.axes.plot(self.x1, self.y1, marker="o", color="#08F7FE")
        for x, y in zip(self.x1, self.y1):
            if y > temp_threshold:
                self.sc1.axes.plot(x, y, marker="o", color="#FE53BB")
                self.sc1.axes.fill_between([x-0.5, x+0.5], y, color="#FE5353", alpha=0.1)
            else:
                self.sc1.axes.plot(x, y, marker="o", color="#08F7FE")
                self.sc1.axes.fill_between([x-0.5, x+0.5], y, color="#08F7FE", alpha=0.1)
        self.sc1.axes.grid(color="#2A3459")
        self.sc1.axes.set_title("Temperature")
        self.sc1.draw()

    def add_temp(self):
        try:
            data = db.child("ESP32").child("Temp").get()
            # if temp != data.val():
            for i in range(len(self.x1) - 1):
                self.y1[i] = self.y1[i + 1]
            self.y1[len(self.y1) - 1] = data.val()
            self.plot_data_temp()
        except Exception as e:
            print(e)
        self.show()

    def plot_data_humid(self):
        global humid_threshold
        self.sc2.axes.clear()
        if self.y2[len(self.y2) - 1] > humid_threshold:
            self.sc2.axes.plot(self.x2, self.y2, marker="o", color="#FE5353")
        else:
            self.sc2.axes.plot(self.x2, self.y2, marker="o", color="#08F7FE")
        for x, y in zip(self.x2, self.y2):
            if y > humid_threshold:
                self.sc2.axes.plot(x, y, marker="o", color="#FE53BB")
                self.sc2.axes.fill_between([x-0.5, x+0.5], y, color="#FE5353", alpha=0.1)
            else:
                self.sc2.axes.plot(x, y, marker="o", color="#08F7FE")
                self.sc2.axes.fill_between([x-0.5, x+0.5], y, color="#08F7FE", alpha=0.1)
        self.sc2.axes.grid(color="#2A3459")
        self.sc2.axes.set_title("Humidity")
        self.sc2.draw()

    def add_humid(self):
        try:
            data = db.child("ESP32").child("Humid").get()
            # if humid != data.val():
            for i in range(len(self.x2) - 1):
                self.y2[i] = self.y2[i + 1]
            self.y2[len(self.y2) - 1] = data.val()
            self.plot_data_humid()
        except Exception as e:
            print(e)
        self.show()

    def warning_threshold(self):
        code = 0
        if temp_threshold < temp.val():
            code += 10
        if humid_threshold < humid.val():
            code += 1
        if code == 0:
            self.ui.label_57.setStyleSheet("color:rgb(0, 255, 0)")
            self.ui.label_57.setText("LOW TEMP - LOW HUMID")
        elif code == 1:
            self.ui.label_57.setStyleSheet("color:rgb(255, 0, 0)")
            self.ui.label_57.setText("HIGH HUMID")
        elif code == 10:
            self.ui.label_57.setStyleSheet("color:rgb(255, 0, 0)")
            self.ui.label_57.setText("HIGH TEMP")
        else:
            self.ui.label_57.setStyleSheet("color:rgb(255, 0, 0)")
            self.ui.label_57.setText("HIGH TEMP - HIGH HUMID")
        

     
     
    def show_graph(self):
        current_page = self.ui.stackedWidget_2.currentWidget().objectName()
        if current_page == "page_1_1":
            self.ui.stackedWidget_2.setCurrentWidget(self.ui.page_1_2)
        else:
            self.ui.stackedWidget_2.setCurrentWidget(self.ui.page_1_1)
        graph_thread = threading.Thread(target=self.add_graph_db)
        graph_thread.start()

    def plot_graph_db(self, arrx, arry, whatdata):
        global temp_threshold
        global humid_threshold
        try:
            if whatdata == "temp":
                self.sc3.axes.clear()
                if arry[len(arry) - 1] > temp_threshold:
                    self.sc3.axes.plot(arrx, arry, marker="o", color="#FE5353")
                else:
                    self.sc3.axes.plot(arrx, arry, marker="o", color="#08F7FE")
                for x, y in zip(arrx, arry):
                    if y > temp_threshold:
                        print(x)
                        self.sc3.axes.plot(x, y, marker="o", color="#FE53BB")
                        self.sc3.axes.fill_between([x-0.5, x+0.5], y, color="#FE5353", alpha=0.1)
                    else:
                        print(x)
                        self.sc3.axes.plot(x, y, marker="o", color="#08F7FE")
                        self.sc3.axes.fill_between([x-0.5, x+0.5], y, color="#08F7FE", alpha=0.1)
                self.sc3.axes.grid(color="#2A3459")
                self.sc3.axes.set_title("Temperature")
                self.sc3.draw()
            elif whatdata == "humid":
                self.sc4.axes.clear()
                if arry[len(arry) - 1] > humid_threshold:
                    self.sc4.axes.plot(arrx, arry, marker="o", color="#FE5353")
                else:
                    self.sc4.axes.plot(arrx, arry, marker="o", color="#08F7FE")
                for x, y in zip(arrx, arry):
                    if y > humid_threshold:
                        self.sc4.axes.plot(x, y, marker="o", color="#FE53BB")
                        self.sc4.axes.fill_between([x-0.5, x+0.5], y, color="#FE5353", alpha=0.1)
                    else:
                        self.sc4.axes.plot(x, y, marker="o", color="#08F7FE")
                        self.sc4.axes.fill_between([x-0.5, x+0.5], y, color="#08F7FE", alpha=0.1)
                self.sc4.axes.grid(color="#2A3459")
                self.sc4.axes.set_title("Humidity")
                self.sc4.draw()
        except Exception as e:
            print(e)
        
    def add_graph_db(self):
        global search_time
        try:
            obj = dataCollection(self.pathdb, self.pathcsv, self.database)
            area = self.ui.textEdit_28.toPlainText()
            if area != "":
                rows = obj.search_database_area(search_time[0:19], search_time[19:39], area)
            else:
                rows = obj.search_database(search_time[0:19], search_time[19:39])
            arr_x = []
            arr_y = []
            cnt = 0
            for i in range(len(rows)):
                arr_y.append(rows[i][0])
                arr_x.append(cnt)
                cnt += 1
            self.plot_graph_db(arr_x, arr_y, "temp")
            arr_x = []
            arr_y = []
            cnt = 0
            for i in range(len(rows)):
                arr_y.append(rows[i][1])
                arr_x.append(cnt)
                cnt += 1
            self.plot_graph_db(arr_x, arr_y, "humid")
            self.show()
        except Exception as e:
            print(f"Exception error at add_graph_db: {e}")

################################################
########### create and execute database ########
################################################

    def add_db(self):
        global time
        obj = dataCollection(self.pathdb, self.pathcsv, self.database)
        obj.infomations.Humidity = db.child("ESP32").child("Humid").get().val()
        obj.infomations.Temperature = db.child("ESP32").child("Temp").get().val()
        obj.infomations.Time = time
        obj.infomations.Area = self.area_by_distance()
        obj.insert_database()

    def area_by_distance(self):
        min = 99999
        cnt = 0
        min_cnt = 0
        file_path = os.path.join(os.path.dirname(__file__), "coordinates.json")
        locations = json.load(open(file_path, "r"))
        for location in locations:
            cnt += 1
            coords_1 = (location["latitude"], location["longitude"])
            coords_2 = (
                db.child("GPS").child("Latitude").get().val(),
                db.child("GPS").child("Longitude").get().val(),
            )
            distance = geopy.distance.geodesic(coords_1, coords_2).m
            if min > distance:
                min = distance
                min_cnt = cnt
        return min_cnt


    def add_table_item(self):
        global search_time
        obj = dataCollection(self.pathdb, self.pathcsv, self.database)
        hour = self.ui.textEdit_21.toPlainText()
        min = self.ui.textEdit_22.toPlainText()
        second = self.ui.textEdit_23.toPlainText()
        day = self.ui.textEdit_20.toPlainText()
        month = self.ui.textEdit_18.toPlainText()
        year = self.ui.textEdit_19.toPlainText()
        starttime = (
            str(day)
            + ":"
            + str(month)
            + ":"
            + str(year)
            + " "
            + str(hour)
            + ":"
            + str(min)
            + ":"
            + str(second)
        )
        hour = self.ui.textEdit_24.toPlainText()
        min = self.ui.textEdit_25.toPlainText()
        second = self.ui.textEdit_26.toPlainText()
        day = self.ui.textEdit_32.toPlainText()
        month = self.ui.textEdit_33.toPlainText()
        year = self.ui.textEdit_34.toPlainText()
        endtime = (
            str(day)
            + ":"
            + str(month)
            + ":"
            + str(year)
            + " "
            + str(hour)
            + ":"
            + str(min)
            + ":"
            + str(second)
        )
        search_time = starttime + endtime
        area = self.ui.textEdit_28.toPlainText()
        if area != "":
            rows = obj.search_database_area(starttime, endtime, area)
        else:
            rows = obj.search_database(starttime, endtime)
    
        while self.ui.tableWidget.rowCount() > 0:
            self.ui.tableWidget.removeRow(0)
        no_row = 0
        self.ui.tableWidget.setRowCount(len(rows))
        for row in rows:
            try:
                self.ui.tableWidget.setItem(no_row, 0, QTableWidgetItem(str(row[0])))
                self.ui.tableWidget.setItem(no_row, 1, QTableWidgetItem(str(row[1])))
                self.ui.tableWidget.setItem(no_row, 2, QTableWidgetItem(str(row[2])))
                self.ui.tableWidget.setItem(no_row, 3, QTableWidgetItem(str(row[3])))
            except Exception as e:
                print(e)
            no_row += 1
    
    def export_csvfile(self):
        try:
            obj = dataCollection(self.pathdb, self.pathcsv, self.database)
            obj.export_CSV()
        except Exception as e:
            print(e)

    def save_setting(self):
        try:
            self.write_setting()
        except Exception as e:
            print(e)

    def send_enable(self):
        if db.child("CAR").child("ENABLE").get().val() == "OFF":
            file_path = os.path.join(os.path.dirname(__file__), "coordinates.json")
            locations = json.load(open(file_path, "r"))
            if len(locations) == 0:
                return
            self.count = 0
            db.child("CAR").update({"Latitude": str(locations[self.count]["latitude"])})
            db.child("CAR").update({"Longitude": str(locations[self.count]["longitude"])})
            self.count = 1
            # try:
            #     if self.count < self.final_waypoint:
            #         db.child("CAR").update({"Latitude": str(locations[self.count]["latitude"])})
            #         db.child("CAR").update({"Longitude": str(locations[self.count]["longitude"])})
            #         self.count += 1
            # except Exception as e:
                # print(f"Exception error at send_enable: {e}")
            db.child("CAR").update({"ENABLE": "ON"})
            self.ui.pushButton_12.setStyleSheet(
                "QPushButton {\n"
                "    background-color: #6ed500;\n"
                "    border: 2px solid #6ed500;\n"
                "    color: white;\n"
                "    font-size: 18px;\n"
                "    padding: 8px 16px;\n"
                "    border-radius: 5px;\n"
                "}\n"
                "\n"
                "QPushButton:hover {\n"
                "    background-color: lightgreen;\n"
                "    border: 2px solid lightgreen;\n"
                "    color: black;\n"
                "}\n"
                "\n"
                "QPushButton:pressed {\n"
                "    background-color: darkgreen;\n"
                "    border: 2px solid darkgreen;\n"
                "    color: white;\n"
                "    padding-top: 10px;\n"
                "    padding-bottom: 6px;\n"
                "}"
            )
        else:
            db.child("CAR").update({"ENABLE": "OFF"})
            self.ui.pushButton_12.setStyleSheet(
                "QPushButton {\n"
                "    background-color: #f8d568;\n"
                "    border: 2px solid #f8d568;\n"
                "    color: white;\n"
                "    font-size: 18px;\n"
                "    padding: 8px 16px;\n"
                "    border-radius: 5px;\n"
                "}\n"
                "\n"
                "QPushButton:hover {\n"
                "    background-color: #ffe06b;\n"
                "    border: 2px solid #ffe06b;\n"
                "    color: black;\n"
                "}\n"
                "\n"
                "QPushButton:pressed {\n"
                "    background-color: #ffc107;\n"
                "    border: 2px solid #ffc107;\n"
                "    color: white;\n"
                "    padding-top: 10px;\n"
                "    padding-bottom: 6px;\n"
                "}"
            )
    
    def read_setting(self):
        file_path = os.path.join(os.path.dirname(__file__), "setting.json")
        settings = json.load(open(file_path, "r"))
        self.pathdb = settings["pathdb"]
        self.pathcsv = settings["pathcsv"]
        self.database = settings["dbname"]
        

    def write_setting(self):
        file_path = os.path.join(os.path.dirname(__file__), "setting.json")
        settings = {
            "pathdb" : self.ui.textEdit_5.toPlainText(),
            "pathcsv" : self.ui.textEdit_6.toPlainText(),
            "dbname" : self.ui.textEdit_4.toPlainText()
        }
        json.dump(settings, open(file_path, "w"))
        self.read_setting()


    def send_email(self):
        # Define email sender and receiver
        email_sender = 'tuoxen20@gmail.com'
        email_password = 'nbazapayqbanbqsg'
        email_receiver = 'tunguyendeleter@gmail.com'
        # Set the subject and body of the email
        try:
            name = self.ui.lineEdit_3.text()
            email = self.ui.lineEdit_4.text()
            phone = self.ui.lineEdit_5.text()
            subject = name + " - " + email + " - " + phone
            body = self.ui.textEdit.toPlainText()
            em = EmailMessage()
            em['From'] = email_sender
            em['To'] = email_receiver
            em['Subject'] = subject
            em.set_content(body)

            # Add SSL (layer of security)
            context = ssl.create_default_context()

            # Log in and send the email
            with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context) as smtp:
                smtp.login(email_sender, email_password)
                smtp.sendmail(email_sender, email_receiver, em.as_string())
        except Exception as e:
            print(e)


    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            event.accept()

################################################
############### execute app ####################
################################################

# # LOGIN AUTHENTICATION PAGE
# class myLogin(QWidget):
#     def __init__(self, queue):
#         super().__init__()
#         self.login = Ui_Form()
#         self.login.setupUi(self)
#         self.login.pushButton.clicked.connect(self.checkCredential)
#         self.login.label.hide()
#         self.queue = queue

#     def checkCredential(self):
#         username = self.login.username.text()
#         password = self.login.password.text()
#         try: 
#             auth = firebase.auth()
#             # Log the user in
#             auth.sign_in_with_email_and_password(username, password)
#             print("login successfully")
#             self.queue.put('done')
#             self.close()
#         except:
#             self.login.label.show()
#             print("login fail")

# def run_first_app(queue):
#     app = QApplication(sys.argv)
#     first_app = myLogin(queue)
#     first_app.setWindowFlags(QtCore.Qt.FramelessWindowHint)
#     first_app.setAttribute(QtCore.Qt.WA_TranslucentBackground)
#     first_app.show()
#     sys.exit(app.exec_())

# def run_second_app():
#     app = QApplication(sys.argv)
#     second_app = MainWindow()
#     second_app.setWindowFlags(QtCore.Qt.FramelessWindowHint)
#     second_app.setAttribute(QtCore.Qt.WA_TranslucentBackground)
#     second_app.show()
#     sys.exit(app.exec_())

# if __name__ == '__main__':
#     queue = Queue()

#     first_app_process = Process(target=run_first_app, args=(queue,))
#     second_app_process = Process(target=run_second_app)

#     first_app_process.start()
#     first_app_process.join()

#     if not queue.empty() and queue.get() == 'done':
#         second_app_process.start()
#         second_app_process.join()

################################################
############### execute app ####################
################################################


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.setWindowFlags(QtCore.Qt.FramelessWindowHint)
    window.setAttribute(QtCore.Qt.WA_TranslucentBackground)
    window.show()
    sys.exit(app.exec_())

################################################
################### END ########################
################################################