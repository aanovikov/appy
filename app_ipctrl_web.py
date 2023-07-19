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
from queue import Queue
from urllib.parse import urlparse, parse_qs

# os.environ['ANDROID_HOME'] = "/home/android_sdk"
# os.environ['JAVA_HOME'] = "/usr/lib/jvm/java-16-openjdk-amd64"

# Configure logging
#logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=self.logger.info)

# Maximum attempts to locate the element
max_attempts = 3

def battery_opt():
    command = ["adb", "shell", "am", "start", "-a", "android.settings.IGNORE_BATTERY_OPTIMIZATION_SETTINGS"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if stdout:
        self.logger.info("Output: ", stdout.decode())
    if stderr:
        self.logger.info("Error: ", stderr.decode())

def open_iproxy(device_serial, device_id, logger):
    # Run the ADB command to check the focused application
    adb_command = f'adb -s {device_serial} shell dumpsys window windows | grep -E "mCurrentFocus|mFocusedApp"'
    process = subprocess.Popen(adb_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    if stderr:
        logger.error('Error: %s', stderr.decode())
        return

    # Check if the output contains the package name
    if b'com.iproxy.android' in stdout:
        logger.info("The application is already on the screen.")
    else:
        # Application is in the background, start it
        start_command = f'adb -s {device_serial} shell am start -n com.iproxy.android/com.iproxy.android.MainActivity'
        start_process = subprocess.Popen(start_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        start_stdout, start_stderr = start_process.communicate()

        if start_stdout:
            logger.info(f"{self.device_id}: Output: %s", start_stdout.decode())
        if start_stderr:
            logger.error('Error: %s', start_stderr.decode())

def reboot(device_serial, device_id, logger):
    try:
        logger.info(f"Rebooting {device_id} with serial {device_serial}")
        adb_command = f'adb -s {device_serial} reboot'
        process = subprocess.Popen(adb_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            logger.error(f"Failed to reboot {device_id} with serial {device_serial}. Error: {stderr.decode()}")
        else:
            logger.info(f"Reboot command successfully executed. Output: {stdout.decode()}")

    except Exception as e:
        logger.error(f"Failed to execute reboot command. Error: {e}")

# Create a queue to store the incoming requests
request_queue = Queue()

class CustomRequestHandler(BaseHTTPRequestHandler):
    # словарь, содержащий очереди для каждого устройства
    device_queues = {}

    def _send_response(self, message):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        try:
            self.wfile.write(message.encode())
        except BrokenPipeError:
            self.logger.info("Client closed the connection before the response could be sent.")
            pass  # or log error message if you prefer
    
    def do_GET(self):
        # Parse URL
        url = urlparse(self.path)

        if url.path == '/api':
            params = parse_qs(url.query)
            device_id = params.get('id', [None])[0]
            pin = params.get('pin', [None])[0]
            device_serial = params.get('srl', [None])[0]

            # Создание новой очереди для устройства, если её ещё нет
            if device_serial not in self.device_queues:
                self.device_queues[device_serial] = Queue()
            
            if params.get('login') == ['true']:
                self.device_queues[device_serial].put((pin, device_id, 'test_login'))
                self._send_response('Login done')

            elif params.get('logout') == ['true']:
                self.device_queues[device_serial].put(('None', device_id, 'test_logout'))  # assuming pin is not required for logout
                self._send_response('Logout done')

            elif params.get('reboot') == ['true']:
                device_id_logger = logging.getLogger(device_id)
                reboot(device_serial, device_id, device_id_logger)  # call reboot function
                self._send_response(f'reboot started for {device_id}')

            else:
                self._send_response('No valid header found')

            # При каждом получении запроса запускаем обработчик заданий
            self.handle_device_requests(device_serial)

    def handle_device_requests(self, device_serial):
        while not self.device_queues[device_serial].empty():
            pin, device_id, test_name = self.device_queues[device_serial].get()

            suite = unittest.TestSuite()
            suite.addTest(TestAppiumWithPin(pin, device_serial, device_id, test_name))
            unittest.TextTestRunner().run(suite)

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

class AlreadyLoggedInException(Exception):
        pass

class TestAppiumWithPin(TestAppium):   
    def __init__(self, pin, device_serial, device_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pin = pin
        self.device_serial = device_serial
        self.device_id = device_id

        # Set up a logger for this device
        self.logger = logging.getLogger(self.device_id)
        self.logger.setLevel(logging.INFO)  # Set logging level to INFO

        if not self.logger.handlers:  # Add handler only if there are no handlers added previously
            handler = logging.StreamHandler()
            formatter = logging.Formatter(f'%(asctime)s %(name)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def setUp(self): #set capabilities for each test separately
        capabilities = dict(
            platformName='Android',
            automationName='uiautomator2',
            udid=self.device_serial,
            deviceName=self.device_id,
        )
        self.appium_server_url = 'http://localhost:4723'  # используем один и тот же URL для всех тестов
        self.driver = webdriver.Remote(self.appium_server_url, capabilities)
        self.wait = WebDriverWait(self.driver, 10)       

    def tearDown(self):
        if self.driver is not None:
            self.driver.quit()

    def test_login(self) -> None:
        max_attempts = 3
        PIN = self.pin  # Consider retrieving this from a more secure place
        self.logger.info('test_login started')
        open_iproxy(self.device_serial, self.device_id, self.logger)
        self.logger.info("iproxy opened")

        for attempt in range(max_attempts):
            try:
                try:
                    self.click_use_pin()
                except NoSuchElementException:
                    self.check_status()
                    break
                self.input_pin(PIN)
                self.click_login()
                self.selecting_connection()
                self.popup_in_use()
                self.selecting_connection()

                # Проверка успешного входа в систему
                try:
                    WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.XPATH, '//android.widget.TextView[@text="Proxy"]')))
                    self.logger.info("Successfully LOGGED IN")

                    #check proxy status
                    proxy_status = self.toggle_status()
                    if proxy_status == "Proxy is disabled":
                        self.proxy_switcher()  # call proxy_switcher if proxy is disabled
                    elif proxy_status == "Proxy is enabled":
                        self.logger.info("Proxy is already enabled")

                    break

                except TimeoutException:
                    self.logger.info("LOGIN unsuccessful. Retrying...")
                    continue

            except (StaleElementReferenceException, NoSuchElementException, TimeoutException) as e:
                self.logger.info(f"Error during login attempt {attempt + 1}: {e}. Retrying...")
                continue
    
    def test_logout(self):
        max_attempts = 3
        self.logger.info("test_logout started")
        open_iproxy(self.device_serial, self.device_id, self.logger)
        self.logger.info("iproxy opened")

        for attempt in range(max_attempts):
            try:
                self.click_more()
                self.chose_logout()
                self.confirm_logout()
                self.signing_out()

                # Проверка успешного входа в систему
                try:
                    logout_status = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.XPATH, '//android.widget.TextView[@text="LOG IN"]')))
                    self.logger.info("Successfully LOGGED OUT")
                    return logout_status.text

                except TimeoutException:
                    self.logger.info("Logout unsuccessful. Retrying...")
                    continue

            except (StaleElementReferenceException, NoSuchElementException, TimeoutException) as e:
                self.logger.info(f"Error during logout attempt {attempt + 1}: {e}. Retrying...")
                continue

    def click_use_pin(self) -> None:
        self.logger.info("starting function 'click_use_pin'")
        usepin_button = self.wait.until(EC.visibility_of_element_located((By.XPATH, '//android.widget.TextView[@text="USE PIN"]')))
        self.logger.info("found button 'USE PIN'")
        usepin_button.click()
        self.logger.info("clicked 'USE PIN'")

    def input_pin(self, PIN: str) -> None:
        self.logger.info("starting function 'input_pin'")
        pin_field = self.driver.find_element(By.XPATH, '//android.widget.ScrollView[@index="0"]/android.widget.EditText[@index="1"]')
        self.logger.info("found input 'Connection PIN'")
        pin_field.clear()
        self.logger.info("input field was cleared")
        pin_field.send_keys(PIN)
        self.logger.info(f'Input {PIN}')

    def click_login(self) -> None:
        self.logger.info("starting function 'click_login'")
        click_login = self.wait.until(EC.visibility_of_element_located((By.XPATH, '//android.widget.TextView[@text="LOG IN"]')))
        self.logger.info("found button 'LOG IN'")
        click_login.click()
        self.logger.info("clicked 'LOG IN'")

    def popup_in_use(self):
        try:
            # Ожидаем появления всплывающего окна в течение 5 секунд
            self.logger.info("starting function 'popup_in_use'")
            popup_continue = WebDriverWait(self.driver, 5).until(EC.visibility_of_element_located((By.XPATH, '//android.widget.TextView[@text="Continue"]')))
            self.logger.info("found button 'continue'")
            popup_continue.click()
            self.logger.info("Clicked continue")
        except TimeoutException:
            # Если всплывающее окно не появилось, продолжаем выполнение кода
            self.logger.info("Popup connection is in use NOT APPEARED")
    
    def selecting_connection(self):
        try:
            # Ожидаем появления всплывающего окна в течение 10 секунд
            self.logger.info("starting function 'selecting_connection'")
            popup_selecting = WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.XPATH, '//android.widget.TextView[@text="Selecting connection…"]')))
            self.logger.info(f"found popup with text {popup_selecting.text}")

            # Ожидаем исчезновения всплывающего окна в течение 30 секунд
            WebDriverWait(self.driver, 30).until(EC.invisibility_of_element_located((By.XPATH, '//android.widget.TextView[@text="Selecting connection…"]')))
            self.logger.info("popup 'selecting_connection' DISSAPEARED")

        except TimeoutException:
            # Если всплывающее окно не появилось, продолжаем выполнение кода
            self.logger.info("Popup 'selecting_connection' NOT APPEARED")

    def toggle_status(self):
        self.logger.info("starting function 'toggle_status'")
        try:
            toggle_status = self.wait.until(EC.visibility_of_element_located((By.XPATH, '//android.widget.ScrollView[@index="0"]/android.view.View[@index="0"]/android.view.View[@index="5"]/android.widget.TextView[@index="1"]')))
            self.logger.info(toggle_status.text)
            return toggle_status.text
        except TimeoutException:
            self.logger.info("Toggle status element not found. Continuing without it...")
            return None

    def proxy_switcher(self):
        self.logger.info("starting function 'proxy_switcher'")
        try:
            proxy_switcher = self.wait.until(EC.visibility_of_element_located((By.XPATH, '//android.widget.ScrollView[@index="0"]/android.view.View[@index="0"]/android.view.View[@index="5"]')))
            self.logger.info("found element proxy_switcher")
            proxy_switcher.click()
            self.logger.info("proxy switched ON")
        except TimeoutException:
            self.logger.info("Toggle status element not found. Continuing without it...")

    def click_more(self):
        self.logger.info("starting function 'click_more'")
        try:
            click_more = self.wait.until(EC.visibility_of_element_located((By.XPATH, '//android.view.View[@content-desc="Options"]')))
            self.logger.info("found element MORE")
            click_more.click()
            self.logger.info("tap MORE")
        except TimeoutException:
            self.logger.info("element MORE not found. Continuing without it...")

    def chose_logout(self):
        self.logger.info("starting function 'chose_logout'")
        try:
            chose_logout = self.wait.until(EC.visibility_of_element_located((By.XPATH, '//android.widget.ScrollView[@index="0"]/android.view.View[@index="6"]/android.widget.TextView[@index="0"]')))
            self.logger.info("found element LOGOUT")
            chose_logout.click()
            self.logger.info("tap LOGOUT")
        except TimeoutException:
            self.logger.info("element LOGOUT not found. Continuing without it...")

    def confirm_logout(self):
        self.logger.info("starting function 'confirm_logout'")
        try:
            confirm_logout = self.wait.until(EC.visibility_of_element_located((By.ID, 'android:id/button1')))
            self.logger.info("found element confirm_LOGOUT")
            confirm_logout.click()
            self.logger.info("tap confirm_LOGOUT")
        except TimeoutException:
            self.logger.info("element confirm_LOGOUT not found. Continuing without it...")

    def signing_out(self):
        try:
            # Ожидаем появления элемента
            self.logger.info("starting function 'signing_out'")
            popup_signing_out = WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located((By.XPATH, '//android.widget.TextView[@text="Signing out…"]')))
            #print(popup_signing_out.text)
            self.logger.info(f"found popup with text {popup_signing_out.text}")

            # Ожидаем, когда элемент станет устаревшим
            WebDriverWait(self.driver, 30).until(EC.staleness_of(popup_signing_out))
            self.logger.info("popup 'signing_out' DISAPPEARED")

        except TimeoutException:
            # Если элемент не появился или не исчез в заданный период времени
            self.logger.info("Popup 'signing_out' NOT APPEARED or DID NOT DISAPPEAR in time")

    def scroll_to_text(driver, text):
        element = driver.find_element(MobileBy.ANDROID_UIAUTOMATOR,
                                    'new UiScrollable(new UiSelector().resourceId("android:id/list")).scrollIntoView(new UiSelector().text("'+ text +'"))')
        return element

    def check_status(self) -> None:
        self.logger.info("starting function 'check_status'")
        try:
            status_text = self.wait.until(EC.visibility_of_element_located((By.XPATH, '//android.widget.TextView[@text="Status"]')))
            self.logger.info("found text 'status'")
            
            if status_text:
                #self.logger.info("You are already logged in.")
                raise AlreadyLoggedInException("You are already logged in.")
            else:
                status_button.click()
                self.logger.info("clicked 'status'")
        except NoSuchElementException:
            self.logger.info("Status element not found. Continuing without it...")

if __name__ == '__main__':
    server_address = ('', 8000)
    httpd = HTTPServer(server_address, CustomRequestHandler)
    httpd.serve_forever()