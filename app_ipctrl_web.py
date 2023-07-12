import unittest
from appium import webdriver
from selenium.webdriver.common.by import By
from appium.webdriver.common.appiumby import AppiumBy
from appium.webdriver.common.mobileby import MobileBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, NoSuchElementException
from appium.webdriver.common.touch_action import TouchAction
from datetime import datetime
import logging
import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from queue import Queue
from urllib.parse import urlparse, parse_qs

os.environ['ANDROID_HOME'] = "/home/android_sdk"
os.environ['JAVA_HOME'] = "/usr/lib/jvm/java-16-openjdk-amd64"

# Configure logging
logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)

# Maximum attempts to locate the element
max_attempts = 3

def battery_opt():
    command = ["adb", "shell", "am", "start", "-a", "android.settings.IGNORE_BATTERY_OPTIMIZATION_SETTINGS"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if stdout:
        logging.info('Output: ', stdout.decode())
    if stderr:
        logging.info('Error: ', stderr.decode())

def scroll_to_text(driver, text):
    element = driver.find_element(MobileBy.ANDROID_UIAUTOMATOR,
                                  'new UiScrollable(new UiSelector().resourceId("android:id/list")).scrollIntoView(new UiSelector().text("'+ text +'"))')
    return element

def open_iproxy():
    # Run the ADB command to check the focused application
    adb_command = 'adb shell dumpsys window windows | grep -E "mCurrentFocus|mFocusedApp"'
    process = subprocess.Popen(adb_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    if stderr:
        logging.error('Error: %s', stderr.decode())
        return

    # Check if the output contains the package name
    if b'com.iproxy.android' in stdout:
        logging.info('The application is already on the screen.')
    else:
        # Application is in the background, start it
        start_command = 'adb shell am start -n com.iproxy.android/com.iproxy.android.MainActivity'
        start_process = subprocess.Popen(start_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        start_stdout, start_stderr = start_process.communicate()

        if start_stdout:
            logging.info('Output: %s', start_stdout.decode())
        if start_stderr:
            logging.error('Error: %s', start_stderr.decode())

# capabilities = dict(
#     platformName='Android',
#     automationName='uiautomator2',
#     deviceName=self.device_name,
# )

appium_server_url = 'http://localhost:4723'

# Create a queue to store the incoming requests
request_queue = Queue()

class CustomRequestHandler(BaseHTTPRequestHandler):
    def _send_response(self, message):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(message.encode())

    def do_GET(self):
        # Parse URL
        url = urlparse(self.path)

        if url.path == '/api':
            params = parse_qs(url.query)
            #id = params.get('id', [None])[0]
            pin = params.get('pin', [None])[0]
            serial = params.get('srl', [None])[0]

            if params.get('login') == ['true']:
                request_queue.put((pin, serial, 'test_login'))
                #suite = unittest.TestSuite()
                #suite.addTest(TestAppiumWithPin(pin, serial, 'test_login'))
                #unittest.TextTestRunner().run(suite)
                self._send_response('Login test started')

            elif params.get('logout') == ['true']:
                request_queue.put(('dummy_pin', serial, 'test_logout'))  # assuming pin is not required for logout
                self._send_response('Logout test added to queue')

            else:
                self._send_response('No valid header found')

def handle_requests():
    while True:
        # If there are tasks in the queue, take one and run it
        if not request_queue.empty():
            pin, serial, test_name = request_queue.get()
            suite = unittest.TestSuite()
            suite.addTest(TestAppiumWithPin(pin, serial, test_name))
            unittest.TextTestRunner().run(suite)
            request_queue.task_done()

request_handler = Thread(target=handle_requests)
request_handler.start()


class TestAppium(unittest.TestCase):
    driver = None
    wait = None

    @classmethod
    def setUpClass(cls) -> None:
        pass
           
    @classmethod
    def tearDownClass(cls) -> None:
        if cls.driver is not None:
            cls.driver.quit()

class TestAppiumWithPin(TestAppium):
    def __init__(self, pin, device_name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pin = pin
        self.device_name = device_name

    #set capabilities for each test separatelly
    def setUp(self):
        capabilities = dict(
            platformName='Android',
            automationName='uiautomator2',
            deviceName=self.device_name,
        )
        self.driver = webdriver.Remote(appium_server_url, capabilities)
        self.wait = WebDriverWait(self.driver, 10)        

    def tearDown(self):
        if self.driver is not None:
            self.driver.quit()

    def test_login(self) -> None:
        max_attempts = 3
        PIN = self.pin  # Consider retrieving this from a more secure place
        logging.info('test_login started')
        open_iproxy()
        logging.info('iproxy opened')

        for attempt in range(max_attempts):
            try:
                self.click_use_pin()
                self.input_pin(PIN)
                self.click_login()
                self.selecting_connection()
                self.popup_in_use()
                self.selecting_connection()
                
                # Проверка успешного входа в систему
                try:
                    WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.XPATH, '//android.widget.TextView[@text="Proxy"]')))
                    logging.info("Successfully LOGGED IN")

                    #check proxy status
                    proxy_status = self.toggle_status()
                    if proxy_status == "Proxy is disabled":
                        self.proxy_switcher()  # call proxy_switcher if proxy is disabled
                    elif proxy_status == "Proxy is enabled":
                        logging.info("Proxy is already enabled")

                    break

                except TimeoutException:
                    logging.info("LOGIN unsuccessful. Retrying...")
                    continue
                
                
            except (StaleElementReferenceException, NoSuchElementException, TimeoutException) as e:
                logging.info(f"Error during login attempt {attempt + 1}: {e}. Retrying...")
                continue

    def test_logout(self):
        max_attempts = 3
        logging.info('test_logout started')
        open_iproxy()
        logging.info('iproxy opened')

        for attempt in range(max_attempts):
            try:
                self.click_more()
                self.chose_logout()
                self.confirm_logout()
                self.signing_out()
                
                # Проверка успешного входа в систему
                try:
                    logout_status = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.XPATH, '//android.widget.TextView[@text="LOG IN"]')))
                    logging.info("Successfully LOGGED OUT")
                    return logout_status.text

                except TimeoutException:
                    logging.info("Logout unsuccessful. Retrying...")
                    continue
                
            except (StaleElementReferenceException, NoSuchElementException, TimeoutException) as e:
                logging.info(f"Error during logout attempt {attempt + 1}: {e}. Retrying...")
                continue

    def click_use_pin(self) -> None:
        logging.info("starting function 'click_use_pin'")
        usepin_button = self.wait.until(EC.visibility_of_element_located((By.XPATH, '//android.widget.TextView[@text="USE PIN"]')))
        logging.info("found button 'USE PIN'")
        usepin_button.click()
        logging.info("clicked 'USE PIN'")

    def input_pin(self, PIN: str) -> None:
        logging.info("starting function 'input_pin'")
        pin_field = self.driver.find_element(By.XPATH, '//android.widget.ScrollView[@index="0"]/android.widget.EditText[@index="1"]')
        logging.info("found input 'Connection PIN'")
        pin_field.clear()
        logging.info("input field was cleared")
        pin_field.send_keys(PIN)
        logging.info(f'Input {PIN}')

    def click_login(self) -> None:
        logging.info("starting function 'click_login'")
        click_login = self.wait.until(EC.visibility_of_element_located((By.XPATH, '//android.widget.TextView[@text="LOG IN"]')))
        logging.info("found button 'LOG IN'")
        click_login.click()
        logging.info("clicked 'LOG IN'")

    def popup_in_use(self):
        try:
            # Ожидаем появления всплывающего окна в течение 5 секунд
            logging.info("starting function 'popup_in_use'")
            popup_continue = WebDriverWait(self.driver, 5).until(EC.visibility_of_element_located((By.XPATH, '//android.widget.TextView[@text="Continue"]')))
            logging.info("found button 'continue'")
            popup_continue.click()
            logging.info("Clicked continue")
        except TimeoutException:
            # Если всплывающее окно не появилось, продолжаем выполнение кода
            logging.info("Popup connection is in use NOT APPEARED")
    
    def selecting_connection(self):
        try:
            # Ожидаем появления всплывающего окна в течение 10 секунд
            logging.info("starting function 'selecting_connection'")
            popup_selecting = WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.XPATH, '//android.widget.TextView[@text="Selecting connection…"]')))
            logging.info(f"found popup with text {popup_selecting.text}")

            # Ожидаем исчезновения всплывающего окна в течение 15 секунд
            WebDriverWait(self.driver, 30).until(EC.invisibility_of_element_located((By.XPATH, '//android.widget.TextView[@text="Selecting connection…"]')))
            logging.info("popup 'selecting_connection' DISSAPEARED")

        except TimeoutException:
            # Если всплывающее окно не появилось, продолжаем выполнение кода
            logging.info("Popup 'selecting_connection' NOT APPEARED")

    def toggle_status(self):
        logging.info("starting function 'toggle_status'")
        try:
            toggle_status = self.wait.until(EC.visibility_of_element_located((By.XPATH, '//android.widget.ScrollView[@index="0"]/android.view.View[@index="0"]/android.view.View[@index="5"]/android.widget.TextView[@index="1"]')))
            logging.info(toggle_status.text)
            return toggle_status.text
        except TimeoutException:
            logging.info("Toggle status element not found. Continuing without it...")
            return None

    def proxy_switcher(self):
        logging.info("starting function 'proxy_switcher'")
        try:
            proxy_switcher = self.wait.until(EC.visibility_of_element_located((By.XPATH, '//android.widget.ScrollView[@index="0"]/android.view.View[@index="0"]/android.view.View[@index="5"]')))
            logging.info("found element proxy_switcher")
            proxy_switcher.click()
            logging.info("proxy switched ON")
        except TimeoutException:
            logging.info("Toggle status element not found. Continuing without it...")

    def click_more(self):
        logging.info("starting function 'click_more'")
        try:
            click_more = self.wait.until(EC.visibility_of_element_located((By.XPATH, '//android.view.View[@content-desc="Options"]')))
            logging.info("found element MORE")
            click_more.click()
            logging.info("tap MORE")
        except TimeoutException:
            logging.info("element MORE not found. Continuing without it...")

    def chose_logout(self):
        logging.info("starting function 'chose_logout'")
        try:
            chose_logout = self.wait.until(EC.visibility_of_element_located((By.XPATH, '//android.widget.ScrollView[@index="0"]/android.view.View[@index="6"]/android.widget.TextView[@index="0"]')))
            logging.info("found element LOGOUT")
            chose_logout.click()
            logging.info("tap LOGOUT")
        except TimeoutException:
            logging.info("element LOGOUT not found. Continuing without it...")

    def confirm_logout(self):
        logging.info("starting function 'confirm_logout'")
        try:
            confirm_logout = self.wait.until(EC.visibility_of_element_located((By.ID, 'android:id/button1')))
            logging.info("found element confirm_LOGOUT")
            confirm_logout.click()
            logging.info("tap confirm_LOGOUT")
        except TimeoutException:
            logging.info("element confirm_LOGOUT not found. Continuing without it...")

    def signing_out(self):
        try:
            # Ожидаем появления элемента
            logging.info("starting function 'signing_out'")
            popup_signing_out = WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.XPATH, '//android.widget.TextView[@text="Signing out…"]')))
            #print(popup_signing_out.text)
            logging.info(f"found popup with text {popup_signing_out.text}")

            # Ожидаем, когда элемент станет устаревшим
            WebDriverWait(self.driver, 30).until(EC.staleness_of(popup_signing_out))
            logging.info("popup 'signing_out' DISAPPEARED")

        except TimeoutException:
            # Если элемент не появился или не исчез в заданный период времени
            logging.info("Popup 'signing_out' NOT APPEARED or DID NOT DISAPPEAR in time")


if __name__ == '__main__':
    server_address = ('', 8000)
    httpd = HTTPServer(server_address, CustomRequestHandler)
    logging.info('Starting server...')
    httpd.serve_forever()
