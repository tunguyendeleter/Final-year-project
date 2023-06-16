/* ------------including the lib for projec-------------------*/
#include <Wire.h>               //the lib of I2C
#include "TinyGPS++.h"          //the lib of decryption GPS
#include "HardwareSerial.h"     //the lib of UART into Arduino
#include <Adafruit_Sensor.h>    //the lib of sensor of Adafruit
#include <Adafruit_HMC5883_U.h> //the lib of HMC5883(COMPASS sensor) of Adafruit
#include "FirebaseESP32.h"      //the lib of connect and send data into Firebase
#include "DHT.h"
/*------------------------------------------------------------*/

// Provide the token generation process info.
#include <addons/TokenHelper.h>

// Provide the RTDB payload printing info and other helper functions.
#include <addons/RTDBHelper.h>

/* ---------declaring the global variable and const ----------*/
// Insert your network credentials
#define WIFI_SSID "Vt123"
#define WIFI_PASSWORD "12345678"

// Insert Firebase project API Key
#define API_KEY "AIzaSyCcJvWUMsUggTU6AtDepoyArvL2MANKyoo"

// Insert Authorized Username and Corresponding Password
#define USER_EMAIL "tunguyendeleter@gmail.com"
#define USER_PASSWORD "89776100"

// Insert RTDB URLefine the RTDB URL
#define DATABASE_URL "https://rtos-62f4e-default-rtdb.asia-southeast1.firebasedatabase.app/"

Adafruit_HMC5883_Unified mag = Adafruit_HMC5883_Unified(12345); // declaring the address of I2C (12345)
TinyGPSPlus gps;                                                // use to read data from GPS
HardwareSerial SerialGPS(1);                                    // connect the GPS with ESP32 through the uart1 (RX1,TX1)
// Define Firebase Data object
FirebaseData fbdo;
FirebaseData stream;

FirebaseAuth auth;
FirebaseConfig config;

String parentPath = "CAR/";
String childPath[3] = {"/ENABLE", "/Latitude", "/Longitude"};

const int trigPin = 5;
const int echoPin = 18;
const float offsetX = 11.32;
const float offsetY = -9.05;
// define sound speed in cm/uS
#define SOUND_SPEED 0.034
#define DHTPIN 32 // what digital pin the DHT sensor is connected to

#define DHTTYPE DHT11 // there are multiple kinds of DHT sensors
DHT dht(DHTPIN, DHTTYPE);

long duration;

// Motor A
int motor1Pin1 = 27;
int motor1Pin2 = 26;
int enable1Pin1 = 14;
// Motor B
int motor1Pin1B = 33;
int motor1Pin2B = 25;
int enable1Pin2 = 12;

int currentheading = 0;
int desiredheading = 0;
double distanceInMeters;
unsigned long distanceGPS = 99;
String check_enable = "OFF";
double lat2;
double long2;

/*------------------------------------------------------------*/

/* ---------------------------------------------------------declaring the function --------------------------------------------------------------------------------*/

void send_temp_humid()
{
    float hum = dht.readHumidity();
    // Read temperature as Celsius (the default)
    float tem = dht.readTemperature();
    if (isnan(hum) || isnan(tem))
    {
        Serial.println("Failed to read from DHT sensor!");
    }
    else
    {
        Firebase.setFloat(fbdo, "/ESP32/Humid", hum);
        Firebase.setFloat(fbdo, "/ESP32/Temp", tem);
        Serial.print(F("Humidity: "));
        Serial.print(hum);
        Serial.print(F("%  Temperature: "));
        Serial.print(tem);
        Serial.println(F("°C "));
    }
}

double toDouble(String nums)
{
    int count1 = 0;
    int count2 = 0;
    int before = 0;
    unsigned long after = 0;
    int i = 0;
    bool check = false;
    int len = nums.length();
    while (i < len)
    {
        if (!check)
        {
            count1++;
        }
        else
        {
            count2++;
        }
        if (nums[i + 1] == '.')
        {
            i++;
            check = true;
        }
        i++;
    }
    int temp = count1 - 1;
    for (int j = 0; j < count1; j++)
    {
        before += pow(10, temp) * (nums[j] - 48);
        temp--;
    }
    if (count2 > 9)
        count2 = 9;
    temp = count2 - 1;
    for (int j = count1 + 1; j < count2 + count1 + 1; j++)
    {
        after += pow(10, temp) * (nums[j] - 48);
        temp--;
    }
    return before + (double)after / (pow(10, count2));
}
/* -----------------Pushing the Firebase- --------------------*/
void updateStatus(void)
{
    String stat;
    stopcar();
    Firebase.setString(fbdo, "/STATUS", "STOP");
    do
    {
        if (Firebase.getString(fbdo, "/STATUS"))
        {
            if (fbdo.dataTypeEnum() == fb_esp_rtdb_data_type_string)
            {
                stat = fbdo.to<String>();
            }
        }
    } while (stat == "STOP");
    if (stat == "PAUSE")
    {
        stopcar();
        while (stat == "PAUSE")
        {
            if (Firebase.getString(fbdo, "/STATUS"))
            {
                if (fbdo.dataTypeEnum() == fb_esp_rtdb_data_type_string)
                {
                    stat = fbdo.to<String>();
                }
            }
        }
    }
    while (SerialGPS.available() > 0)
    {
        gps.encode(SerialGPS.read());
    }
    distanceGPS = gps.distanceBetween(gps.location.lat(), gps.location.lng(), lat2, long2);
}

void wifiinit(void) // create the connect to Firebase
{
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.print("Connecting to Wi-Fi");
    while (WiFi.status() != WL_CONNECTED)
    {
        Serial.print(".");
        delay(300);
    }
    Serial.println();
    Serial.print("Connected with IP: ");
    Serial.println(WiFi.localIP());
    Serial.println();
}

void streamCallback(MultiPathStreamData stream)
{
    if (stream.get(childPath[0]))
    {
        check_enable = stream.value;
        Serial.println(stream.value);
    }
    else if (stream.get(childPath[1]))
    {
        lat2 = toDouble(stream.value);
        Serial.println(stream.value);
    }
    else if (stream.get(childPath[2]))
    {
        long2 = toDouble(stream.value);
        Serial.println(stream.value);
    }
    Serial.println();
    Serial.printf("Received stream payload size: %d (Max. %d)\n\n", stream.payloadLength(), stream.maxPayloadLength());
}

void streamTimeoutCallback(bool timeout)
{
    if (timeout)
        Serial.println("stream timed out, resuming...\n");

    if (!stream.httpConnected())
        Serial.printf("error code: %d, reason: %s\n\n", stream.httpCode(), stream.errorReason().c_str());
}

void firebaseinit(void) // create the connect to Firebase
{
    /* Assign the api key (required) */
    config.api_key = API_KEY;

    /* Assign the user sign in credentials */
    auth.user.email = USER_EMAIL;
    auth.user.password = USER_PASSWORD;

    /* Assign the RTDB URL (required) */
    config.database_url = DATABASE_URL;

    /* Assign the callback function for the long running token generation task */
    config.token_status_callback = tokenStatusCallback; // see addons/TokenHelper.h

    Firebase.begin(&config, &auth);

    Firebase.reconnectWiFi(true);

    if (!Firebase.beginMultiPathStream(stream, parentPath))
        Serial.printf("sream begin error, %s\n\n", stream.errorReason().c_str());

    Firebase.setMultiPathStreamCallback(stream, streamCallback, streamTimeoutCallback);
}

/*------------------------------------------------------------*/

/* -----------------declaring the compass---------------------*/
void initcompass(void) // creating the connect with compass sensor(hmc5883) of lib adfruit
{
    /* Initialise the sensor */
    if (!mag.begin()) // declearing the compass sensor(HMC5883)
    {
        Serial.println("Ooops, no HMC5883 detected ... Check your wiring!"); // There was a problem detecting the HMC5883 ... check your connections
    }
}
/* -----------------angle calculation---------------------*/

int remove_90degree(int a)
{
    a -= 90;
    if (a < 0)
        a += 360;
    return a;
}
int add_90degree(int a)
{
    a += 90;
    if (a > 360)
        a -= 360;
    return a;
}

int getcompass(void) // to reading the current heading in degrees
{
    sensors_event_t event; // creating a sensor event variable which is used to store the magnetic sensor readings
    mag.getEvent(&event);  // get the latest magnetic sensor readings and stores them in the event variable
    float x = event.magnetic.x - offsetX;
    float y = event.magnetic.y - offsetY;
    Serial.print("X: ");
    Serial.print(x);
    Serial.print("  ");
    Serial.print("Y: ");
    Serial.print(y);
    Serial.print("  ");
    Serial.println("uT");
    float heading = atan2(y, x); // calculates the heading using the atan2() function, which calculates the angle in radians between the positive x-axis and the point (x, y).
                                 //    float declinationAngle = 0.0;                              // variable to correct for any magnetic declination in the current location
                                 //    heading += declinationAngle;
    // Correct for when signs are reversed.
    if (heading < 0)
        heading += 2 * PI;
    // Check for wrap due to addition of declination.
    if (heading > 2 * PI)
        heading -= 2 * PI;
    int final_heading = (heading * 180 / M_PI);
    Firebase.setInt(fbdo, "/GPS/Heading", final_heading);
    return final_heading; // converting from radians to degrees
}

int getcompassonly(void) // to reading the current heading in degrees
{
    sensors_event_t event; // creating a sensor event variable which is used to store the magnetic sensor readings
    mag.getEvent(&event);  // get the latest magnetic sensor readings and stores them in the event variable
    float x = event.magnetic.x - offsetX;
    float y = event.magnetic.y - offsetY;
    Serial.print("X: ");
    Serial.print(x);
    Serial.print("  ");
    Serial.print("Y: ");
    Serial.print(y);
    Serial.print("  ");
    Serial.println("uT");
    float heading = atan2(y, x); // calculates the heading using the atan2() function, which calculates the angle in radians between the positive x-axis and the point (x, y).
                                 //    float declinationAngle = 0.0;                              // variable to correct for any magnetic declination in the current location
                                 //    heading += declinationAngle;
    // Correct for when signs are reversed.
    if (heading < 0)
        heading += 2 * PI;
    // Check for wrap due to addition of declination.
    if (heading > 2 * PI)
        heading -= 2 * PI;
    return (int)(heading * 180 / M_PI);
}
/*------------------------------------------------------------*/

/* ---------------------angle calculation---------------------*/
/* --------------------reading data GPS-----------------------*/
void get_coordinates(void)
{
    if (Firebase.getString(fbdo, "/CAR/Latitude"))
    {
        if (fbdo.dataTypeEnum() == fb_esp_rtdb_data_type_string)
        {
            lat2 = toDouble(fbdo.to<String>());
        }
    }
    if (Firebase.getString(fbdo, "/CAR/Longitude"))
    {
        if (fbdo.dataTypeEnum() == fb_esp_rtdb_data_type_string)
        {
            long2 = toDouble(fbdo.to<String>());
        }
    }
}

int getheadingonly(void)
{
    while (SerialGPS.available() > 0)
    {
        gps.encode(SerialGPS.read());
    }
    double heading_lat = gps.location.lat();
    double heading_lng = gps.location.lng();
    Serial.print("LAT1=");
    Serial.println(gps.location.lat(), 10);
    Serial.print("LONG1=");
    Serial.println(gps.location.lng(), 10);
    Serial.print("LAT2=");
    Serial.println(lat2, 10);
    Serial.print("LONG2=");
    Serial.println(long2, 10);
    return (int)(gps.courseTo(heading_lat, heading_lng, lat2, long2));
}

int getheading(void)
{
    while (SerialGPS.available() > 0)
    {
        gps.encode(SerialGPS.read());
    }
    double heading_lat = gps.location.lat();
    double heading_lng = gps.location.lng();
    Serial.print("LAT1=");
    Serial.println(gps.location.lat(), 10);
    Serial.print("LONG1=");
    Serial.println(gps.location.lng(), 10);
    Serial.print("LAT2=");
    Serial.println(lat2, 10);
    Serial.print("LONG2=");
    Serial.println(long2, 10);
    Firebase.setDouble(fbdo, "/GPS/Latitude", heading_lat);
    Firebase.setDouble(fbdo, "/GPS/Longitude", heading_lng);
    distanceGPS = gps.distanceBetween(heading_lat, heading_lng, lat2, long2);
    Serial.print("Distance to destination: ");
    Serial.print(distanceGPS);
    Serial.println(" meters.");
    return (int)(gps.courseTo(heading_lat, heading_lng, lat2, long2));
}
/*------------------------------------------------------------*/

/* -----------------control the motor---------------------*/
void moveforward(void)
{
    // Move forward
    Serial.println("go forward");
    //    digitalWrite(motor1Pin1, LOW);
    //    digitalWrite(motor1Pin2, HIGH);
    //    digitalWrite(motor1Pin1B, LOW);
    //    digitalWrite(motor1Pin2B, HIGH);
    analogWrite(enable1Pin1, 150);
    analogWrite(enable1Pin2, 150);
}

void turnback(void)
{
    // Move back
    Serial.println("go back");
    digitalWrite(motor1Pin1, HIGH);
    digitalWrite(motor1Pin2, LOW);
    digitalWrite(motor1Pin1B, HIGH);
    digitalWrite(motor1Pin2B, LOW);
    analogWrite(enable1Pin1, 140);
    analogWrite(enable1Pin2, 140);
}

void turnright(void)
{
    // Move right
    Serial.println("go right");
    //    digitalWrite(motor1Pin1, LOW);
    //    digitalWrite(motor1Pin2, HIGH);
    //    digitalWrite(motor1Pin1B, LOW);
    //    digitalWrite(motor1Pin2B, HIGH);
    analogWrite(enable1Pin1, 0);
    analogWrite(enable1Pin2, 190);
}

void turnleft(void)
{
    // Move left
    Serial.println("go left");
    //    digitalWrite(motor1Pin1, LOW);
    //    digitalWrite(motor1Pin2, HIGH);
    //    digitalWrite(motor1Pin1B, LOW);
    //    digitalWrite(motor1Pin2B, HIGH);
    analogWrite(enable1Pin1, 190);
    analogWrite(enable1Pin2, 0);
}

void stopcar(void)
{
    // stop
    Serial.println("stop");
    //    digitalWrite(motor1Pin1, LOW);
    //    digitalWrite(motor1Pin2, LOW);
    //    digitalWrite(motor1Pin1B, LOW);
    //    digitalWrite(motor1Pin2B, LOW);
    analogWrite(enable1Pin1, 0);
    analogWrite(enable1Pin2, 0);
}

float GetDistance(void)
{
    float distanceCm = 0;
    // Clears the trigPin
    digitalWrite(trigPin, LOW);
    delayMicroseconds(5);
    // Sets the trigPin on HIGH state for 10 micro seconds
    digitalWrite(trigPin, HIGH);
    delayMicroseconds(10);
    digitalWrite(trigPin, LOW);
    // Reads the echoPin, returns the sound wave travel time in microseconds
    duration = pulseIn(echoPin, HIGH);

    // Calculate the distance
    distanceCm = duration * SOUND_SPEED / 2;
    // Prints the distance in the Serial Monitor
    Serial.print("Distance (cm): ");
    Serial.println(distanceCm);
    return (distanceCm);
}

void checkdistance()
{
    float distance = GetDistance();
    while (distance < 100)
    {
        stopcar();
        delay(100);
        int current_heading = getcompassonly();
        int desired_heading = remove_90degree(current_heading);
        int error = geterror(desired_heading, current_heading);
        while (error > 2 || error < -2)
        {
            while (error > 2)
            {
                turnright();
                delay(100);
                current_heading = getcompassonly();
                error = geterror(desired_heading, current_heading);
            }
            while (error < -2)
            {
                turnleft();
                delay(100);
                current_heading = getcompassonly();
                error = geterror(desired_heading, current_heading);
            }
        }
        moveforward();
        delay(1000);
        current_heading = getcompassonly();
        desired_heading = add_90degree(current_heading);
        error = geterror(desired_heading, current_heading);
        while (error > 2 || error < -2)
        {
            while (error > 2)
            {
                turnright();
                delay(100);
                current_heading = getcompassonly();
                error = geterror(desired_heading, current_heading);
            }
            while (error < -2)
            {
                turnleft();
                delay(100);
                current_heading = getcompassonly();
                error = geterror(desired_heading, current_heading);
            }
        }
        distance = GetDistance();
    }
}

/*------------------------------------------------------------*/
void checkerror(int error)
{
    while (error > 3 || error < -3)
    {
        while (error > 3)
        {
            turnright();
            delay(100);
            currentheading = getcompassonly();
            desiredheading = getheadingonly();
            error = geterror(desiredheading, currentheading);
            Serial.println(error);
            Serial.println("<==============TURN RIGHT=============>");
        }
        while (error < -3)
        {
            turnleft();
            delay(100);
            currentheading = getcompassonly();
            desiredheading = getheadingonly();
            error = geterror(desiredheading, currentheading);
            Serial.println(error);
            Serial.println("<==============TURN LEFT=============>");
        }
    }
    // stopcar();
}

int geterror(int x, int y)
{
    int a = (x - y);
    int b = (y - x);
    if (a < 0)
        a += 360;
    else
        b += 360;
    if (a < b)
        return a;
    else
        return -b;
}
/* -----------------initialize variables, sensors, and other hardware components---------------------*/
void setup(void)
{
    Serial.begin(115200);                      // initialize the serial communication between the board and the computer
    Wire.begin();                              // SDA pin 21, SCL pin 22, 100kHz frequency COMPASS
    SerialGPS.begin(9600, SERIAL_8N1, 16, 17); // gps uart pin 16 RX, 17 TX GPS
    delay(500);                                // allows time for the sensors to initialize before reading data.
    initcompass();                             // to initialize the HMC5883 compass sensor
    wifiinit();
    firebaseinit();
    dht.begin();
    // sets the pins as outputs:
    pinMode(trigPin, OUTPUT); // Sets the trigPin as an Output
    pinMode(echoPin, INPUT);  // Sets the echoPin as an Input
    pinMode(motor1Pin1, OUTPUT);
    pinMode(motor1Pin2, OUTPUT);
    pinMode(enable1Pin1, OUTPUT);
    pinMode(motor1Pin1B, OUTPUT);
    pinMode(motor1Pin2B, OUTPUT);
    pinMode(enable1Pin2, OUTPUT);
    digitalWrite(motor1Pin1, LOW);
    digitalWrite(motor1Pin2, HIGH);
    digitalWrite(motor1Pin1B, LOW);
    digitalWrite(motor1Pin2B, HIGH);
    if (Firebase.getString(fbdo, "/CAR/Longitude"))
    {
        if (fbdo.dataTypeEnum() == fb_esp_rtdb_data_type_string)
        {
            long2 = toDouble(fbdo.to<String>());
        }
    }
    if (Firebase.getString(fbdo, "/CAR/Latitude"))
    {
        if (fbdo.dataTypeEnum() == fb_esp_rtdb_data_type_string)
        {
            lat2 = toDouble(fbdo.to<String>());
        }
    }
}
/*----------------------------------------------------------------------------------------------------*/

void loop()
{
    send_temp_humid();
    if (distanceGPS <= 5)
    {
        updateStatus();
    }
    else if (distanceGPS > 10)
    {
        if (check_enable == "ON")
        {
            /*-------get the heading to caculate the error angle----*/
            currentheading = getcompass();
            desiredheading = getheading();
            int error = geterror(desiredheading, currentheading);
            checkerror(error); // calculate difference of bearing angle and heading angle
            checkdistance();
            moveforward();
            Serial.print("desiredheading: ");
            Serial.println(desiredheading);
            Serial.print("currentheading: ");
            Serial.println(currentheading);
            Serial.print("error: ");
            Serial.println(error);
            Serial.println("<================================>");
        }
        else
        {
            stopcar();
            Serial.println("STOP1");
        }
    }
    else
    {
        if (check_enable == "ON")
        {
            moveforward();
            delay(100);
            while (SerialGPS.available() > 0)
            {
              gps.encode(SerialGPS.read());
            }
            distanceGPS = gps.distanceBetween(gps.location.lat(), gps.location.lng(), lat2, long2);
            Serial.print("Distance to destination: ");
            Serial.print(distanceGPS);
        }
        else
        {
            stopcar();
            Serial.println("STOP2");
        }
    }
}
