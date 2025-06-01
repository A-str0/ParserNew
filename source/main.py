import sys, asyncio, os, json, time
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QTableWidget, QTableWidgetItem,
    QListWidget, QListWidgetItem, QCheckBox, QLabel, QFileDialog,
    QMessageBox, QSpinBox, QGroupBox, QFormLayout, QLineEdit
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from handlers.datetime_handler import current_formatted_time
from handlers.logging_handler import setup_logger
from handlers.format_handler import format_email_subject
from handlers.exceptions import QuitException
from services.bankrupt_parser_service import BankruptParserService
from services.database_service import DatabaseService
from services.email_service import EmailService
from bs4 import BeautifulSoup


class ParserThread(QThread):
    log_signal = pyqtSignal(str)
    result_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal()


    def __init__(self, parser: BankruptParserService, region_ids: list[int], check_publication_date: bool, js_wait_time: int, smtp_config: dict, email_service: EmailService, url_template: str, email_subject_template: str, email_body_template: str, email_interval: int):
        super().__init__()
        self.parser = parser
        self.region_ids = region_ids
        self.check_publication_date = check_publication_date
        self.js_wait_time = js_wait_time
        self.smtp_config = smtp_config
        self.is_running = True
        self.email_service = email_service
        self.url_template = url_template
        self.email_subject_template = email_subject_template
        self.email_body_template = email_body_template
        self.email_interval = email_interval
        self.last_email_time = 0


    def run(self):
        asyncio.run(self.parse())


    async def send_email(self, result: dict):
        # Ensure minimum interval between email sends
        if self.email_interval > 0:
            current_time = time.monotonic()
            elapsed = current_time - self.last_email_time
            if elapsed < self.email_interval:
                await asyncio.sleep(self.email_interval - elapsed)
            self.last_email_time = time.monotonic()

        try:
            # subject = format_email_subject( "Банкротство {} ", inn=result["inn"] )
            subject = self.email_subject_template.format(**result)
            body = self.email_body_template.format(**result)
            self.email_service.send_email(self.smtp_config, subject, body)
            self.log_signal.emit(f"Email sent for INN {result['inn']}")
        except Exception as e:
            self.log_signal.emit(f"Error sending email for INN {result['inn']}: {str(e)}")


    async def parse(self):
        # Parse bankruptcy data for selected regions
        try:
            for region_id in self.region_ids:
                if not self.is_running:
                    self.log_signal.emit("Parser stopped")
                    break

                if not self.parser.db_service.get_region_status(region_id):
                    self.log_signal.emit(f"Region ({region_id}) status is 0, skiping")
                    continue


                self.log_signal.emit(f"Starting parsing for region ID: {region_id}")
                url = self.url_template.format(region_id)
                page = await self.parser.load_page(url, wait_time=self.js_wait_time)
                await page.wait_for_selector("app-bankrupt-result-card-company")

                processed_inns = set()

                while self.is_running:
                    cards = await page.locator("app-bankrupt-result-card-company").all()
                    self.log_signal.emit(f"Found cards: {len(cards)}")
                    new_cards_processed = False

                    for card in cards:
                        if not self.is_running:
                            self.log_signal.emit("Parser stopped")
                            break
                        try:
                            card_soup = BeautifulSoup(await card.inner_html(), "html.parser")
                            self.parser.check_publication_date = self.check_publication_date
                            result = await self.parser.parse_card(page, card_soup, card, wait_time=self.js_wait_time)
                            if result and result["inn"] not in processed_inns:
                                result["region_id"] = region_id
                                processed_inns.add(result["inn"])
                                self.result_signal.emit(result)
                                self.log_signal.emit(f"Processed card: INN={result['inn']}, URL={result['url']}")
                                if result['url']:
                                    await self.send_email(result)
                                new_cards_processed = True
                        except QuitException as e:
                            self.log_signal.emit(str(e))
                            continue
                        except Exception as e:
                            self.log_signal.emit(f"Error processing card: {str(e)}")
                            continue

                    # Pressing button 'Load more'
                    load_more_button = page.get_by_role("button", name="Загрузить еще")
                    if await load_more_button.is_visible() and await load_more_button.is_enabled():
                        if new_cards_processed:
                            self.log_signal.emit("Clicking 'Load More' button")
                            await load_more_button.click()
                            await page.wait_for_timeout(self.js_wait_time)
                        else:
                            self.log_signal.emit("No new cards processed, stopping")
                            break
                    else:
                        self.log_signal.emit("No 'Load More' button or disabled, stopping")
                        break

                if page:
                    await page.close()
        except Exception as e:
            self.log_signal.emit(f"Parsing error: {str(e)}")
        finally:
            self.finished_signal.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Парсер Банкротств")
        self.setGeometry(100, 100, 1200, 800)
        self.parser_thread = None

        # Initialize services
        self.email_service = EmailService()
        self.db_service = DatabaseService()
        self.parser_service = BankruptParserService(db_service=self.db_service)

        # Setup logging
        self.logger = setup_logger("App", "Logs", f"App_Log_{current_formatted_time()}.log")

        # Initialize UI
        self.init_ui()

        # Load regions
        self.populate_region_list()

        # Load last settings
        self.load_last_settings()


    def init_ui(self):
        # Setup the main UI
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Control panel
        control_group = QGroupBox("Управление")
        control_layout = QVBoxLayout()
        control_group.setLayout(control_layout)
        main_layout.addWidget(control_group)

        # Region file selection
        file_layout = QHBoxLayout()
        self.select_file_button = QPushButton("Выбрать файл регионов (!Сбросит таблицу регионов в БД!)")
        self.select_file_button.clicked.connect(self.select_regions_file)
        file_layout.addWidget(self.select_file_button)
        self.file_label = QLabel("Файл не выбран")
        file_layout.addWidget(self.file_label)
        file_layout.addStretch()
        control_layout.addLayout(file_layout)

        # Region selection
        regions_layout = QHBoxLayout()
        self.region_list = QListWidget()
        self.region_list.setSelectionMode(QListWidget.MultiSelection)
        self.region_list.setMinimumHeight(100)
        regions_layout.addWidget(QLabel("Регионы:"))
        regions_layout.addWidget(self.region_list)
        self.select_all_checkbox = QCheckBox("Выбрать все")
        self.select_all_checkbox.stateChanged.connect(self.toggle_select_all)
        regions_layout.addWidget(self.select_all_checkbox)
        control_layout.addLayout(regions_layout)

        # Parser settings
        settings_group = QGroupBox("Настройки парсера")
        settings_layout = QFormLayout()
        settings_group.setLayout(settings_layout)

        self.full_info_checkbox = QCheckBox("Проверять дату последней публикации")
        self.full_info_checkbox.setChecked(True)
        settings_layout.addRow("Режим парсинга:", self.full_info_checkbox)

        self.js_wait_spinbox = QSpinBox()
        self.js_wait_spinbox.setRange(1000, 10000)
        self.js_wait_spinbox.setSingleStep(500)
        self.js_wait_spinbox.setValue(3000)
        self.js_wait_spinbox.setSuffix(" мс")
        settings_layout.addRow("Интервал ожидания JS:", self.js_wait_spinbox)

        self.url_template_edit = QLineEdit()
        self.url_template_edit.setText("https://bankrot.fedresurs.ru/bankrupts?regionId={}&isActiveLegalCase=true&offset=0&limit=100")
        settings_layout.addRow("URL шаблон:", self.url_template_edit)

        self.request_interval_spin = QSpinBox()
        self.request_interval_spin.setRange(0, 60)
        self.request_interval_spin.setValue(5)
        self.request_interval_spin.setSuffix(" с")
        settings_layout.addRow("Интервал запросов:", self.request_interval_spin)

        control_layout.addWidget(settings_group)

        # Email settings
        email_group = QGroupBox("Настройки отправки писем")
        email_layout = QFormLayout()
        email_group.setLayout(email_layout)

        self.smtp_host_edit = QLineEdit()
        self.smtp_host_edit.setText("smtp.yandex.ru")
        email_layout.addRow("SMTP Хост:", self.smtp_host_edit)

        self.smtp_port_edit = QLineEdit()
        self.smtp_port_edit.setText("587")
        email_layout.addRow("SMTP Порт:", self.smtp_port_edit)

        self.email_user_edit = QLineEdit()
        email_layout.addRow("Email Пользователь:", self.email_user_edit)

        self.email_pass_edit = QLineEdit()
        self.email_pass_edit.setEchoMode(QLineEdit.Password)
        email_layout.addRow("Пароль:", self.email_pass_edit)

        self.email_recipient_edit = QLineEdit()
        email_layout.addRow("Получатель:", self.email_recipient_edit)

        self.email_subject_template_edit = QLineEdit()
        self.email_subject_template_edit.setText("Банкротство {inn}")
        self.email_subject_template_edit.setToolTip("Доступные заполнители: {inn}, {status}, {url}, {region_id}")
        email_layout.addRow("Шаблон темы:", self.email_subject_template_edit)

        self.email_body_template_edit = QLineEdit()
        self.email_body_template_edit.setText("Ссылка на публикацию: {url}")
        self.email_body_template_edit.setToolTip("Доступные заполнители: {inn}, {status}, {url}, {region_id}")
        email_layout.addRow("Шаблон тела:", self.email_body_template_edit)

        self.email_interval_spin = QSpinBox()
        self.email_interval_spin.setRange(0, 60)
        self.email_interval_spin.setValue(10)
        self.email_interval_spin.setSuffix(" с")
        email_layout.addRow("Интервал email:", self.email_interval_spin)

        control_layout.addWidget(email_group)

        # Control buttons
        parser_control_layout = QHBoxLayout()
        self.start_button = QPushButton("Запустить парсер")
        self.start_button.clicked.connect(self.start_parsing)
        parser_control_layout.addWidget(self.start_button)
        self.stop_button = QPushButton("Остановить парсер")
        self.stop_button.clicked.connect(self.stop_parsing)
        self.stop_button.setEnabled(False)
        parser_control_layout.addWidget(self.stop_button)
        parser_control_layout.addStretch()
        control_layout.addLayout(parser_control_layout)

        # Settings buttons
        settings_buttons_layout = QHBoxLayout()
        self.save_settings_button = QPushButton("Сохранить настройки")
        self.save_settings_button.clicked.connect(self.save_settings)
        settings_buttons_layout.addWidget(self.save_settings_button)
        self.load_settings_button = QPushButton("Загрузить настройки")
        self.load_settings_button.clicked.connect(self.load_settings)
        settings_buttons_layout.addWidget(self.load_settings_button)
        settings_buttons_layout.addStretch()
        control_layout.addLayout(settings_buttons_layout)

        # Results table
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(4)
        self.result_table.setHorizontalHeaderLabels(["ИНН", "Статус", "URL", "Регион ID"])
        self.result_table.setRowCount(0)
        self.result_table.setColumnWidth(0, 150)
        self.result_table.setColumnWidth(1, 100)
        self.result_table.setColumnWidth(2, 600)
        self.result_table.setColumnWidth(3, 100)
        main_layout.addWidget(self.result_table)

        # Log area
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setFont(QFont("Courier", 10))
        self.log_area.setMinimumHeight(200)
        main_layout.addWidget(self.log_area)


    def select_regions_file(self):
        # Open file dialog to select regions file and load it into DB
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выбрать файл регионов", "", "Текстовые файлы (*.txt)"
        )
        if file_path:
            try:
                self.db_service.clear_regions()
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and " - " in line:
                            name, region_id = line.split(" - ")
                            region_id = int(region_id.strip())
                            self.db_service.insert_region(region_id, name.strip())
                self.logger.info(f"Regions loaded from {file_path} into DB")
                self.file_label.setText(os.path.basename(file_path))
                self.populate_region_list()
            except Exception as e:
                self.logger.error(f"Error loading regions from {file_path}: {e}")
                QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить регионы: {str(e)}")


    def populate_region_list(self):
        # Populate region list from database
        self.region_list.clear()
        try:
            regions = self.db_service.get_regions()
            if not regions:
                self.logger.warning("No regions found in database")
                self.file_label.setText("Файл не выбран, регионы отсутствуют")
            for region_id, name in regions:
                item = QListWidgetItem(f"{name} ({region_id})")
                item.setData(Qt.UserRole, region_id)
                self.region_list.addItem(item)
        except Exception as e:
            self.logger.error(f"Error populating region list: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить регионы: {str(e)}")


    def toggle_select_all(self, state):
        # Select or deselect all regions
        for i in range(self.region_list.count()):
            item = self.region_list.item(i)
            item.setSelected(state == Qt.Checked)


    def save_settings(self):
        # Save current settings to a JSON file
        file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить настройки", "", "JSON файлы (*.json)")
        if file_path:
            try:
                settings = {
                    "url_template": self.url_template_edit.text(),
                    "email_subject_template": self.email_subject_template_edit.text(),
                    "email_body_template": self.email_body_template_edit.text(),
                    "request_interval": self.request_interval_spin.value(),
                    "email_interval": self.email_interval_spin.value(),
                    "smtp_host": self.smtp_host_edit.text(),
                    "smtp_port": self.smtp_port_edit.text(),
                    "email_user": self.email_user_edit.text(),
                    "email_password": self.email_pass_edit.text(),
                    "email_recipient": self.email_recipient_edit.text(),
                    "parse_full_info": self.full_info_checkbox.isChecked(),
                    "js_wait_time": self.js_wait_spinbox.value()
                }
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(settings, f, ensure_ascii=False, indent=4)
                with open("last_settings.json", "w", encoding="utf-8") as f:
                    json.dump(settings, f, ensure_ascii=False, indent=4)
                self.logger.info(f"Settings saved to {file_path}")
            except Exception as e:
                self.logger.error(f"Error saving settings: {e}")
                QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить настройки: {e}")


    def load_settings(self):
        # Load settings from a JSON file
        file_path, _ = QFileDialog.getOpenFileName(self, "Загрузить настройки", "", "JSON файлы (*.json)")
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                self.url_template_edit.setText(settings.get("url_template", ""))
                self.email_subject_template_edit.setText(settings.get("email_subject_template", ""))
                self.email_body_template_edit.setText(settings.get("email_body_template", ""))
                self.request_interval_spin.setValue(settings.get("request_interval", 5))
                self.email_interval_spin.setValue(settings.get("email_interval", 10))
                self.smtp_host_edit.setText(settings.get("smtp_host", ""))
                self.smtp_port_edit.setText(settings.get("smtp_port", "587"))
                self.email_user_edit.setText(settings.get("email_user", ""))
                self.email_pass_edit.setText(settings.get("email_password", ""))
                self.email_recipient_edit.setText(settings.get("email_recipient", ""))
                self.full_info_checkbox.setChecked(settings.get("parse_full_info", True))
                self.js_wait_spinbox.setValue(settings.get("js_wait_time", 3000))
                self.logger.info(f"Settings loaded from {file_path}")
            except Exception as e:
                self.logger.error(f"Error loading settings: {e}")
                QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить настройки: {e}")


    def load_last_settings(self):
        # Load last saved settings
        last_settings_file = "last_settings.json"
        if os.path.exists(last_settings_file):
            try:
                with open(last_settings_file, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                self.url_template_edit.setText(settings.get("url_template", ""))
                self.email_subject_template_edit.setText(settings.get("email_subject_template", ""))
                self.email_body_template_edit.setText(settings.get("email_body_template", ""))
                self.request_interval_spin.setValue(settings.get("request_interval", 5))
                self.email_interval_spin.setValue(settings.get("email_interval", 10))
                self.smtp_host_edit.setText(settings.get("smtp_host", ""))
                self.smtp_port_edit.setText(settings.get("smtp_port", "587"))
                self.email_user_edit.setText(settings.get("email_user", ""))
                self.email_pass_edit.setText(settings.get("email_password", ""))
                self.email_recipient_edit.setText(settings.get("email_recipient", ""))
                self.full_info_checkbox.setChecked(settings.get("parse_full_info", True))
                self.js_wait_spinbox.setValue(settings.get("js_wait_time", 3000))
                self.logger.info("Loaded last settings")
            except Exception as e:
                self.logger.error(f"Error loading last settings: {e}")


    def start_parsing(self):
        # Start parsing for selected regions
        selected_items = self.region_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Ошибка", "Выберите хотя бы один регион")
            return

        region_ids = [item.data(Qt.UserRole) for item in selected_items]
        self.logger.info(f"Starting parsing for regions: {region_ids}")

        # Collect SMTP settings
        smtp_config = {
            "smtp_server": self.smtp_host_edit.text(),
            "smtp_port": int(self.smtp_port_edit.text()) if self.smtp_port_edit.text().isdigit() else 587,
            "user": self.email_user_edit.text(),
            "password": self.email_pass_edit.text(),
            "recipient": self.email_recipient_edit.text()
        }

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.result_table.setRowCount(0)

        self.parser_service.set_request_interval(self.request_interval_spin.value())
        self.parser_thread = ParserThread(
            self.parser_service,
            region_ids,
            self.full_info_checkbox.isChecked(),
            self.js_wait_spinbox.value(),
            smtp_config,
            self.email_service,
            self.url_template_edit.text(),
            self.email_subject_template_edit.text(),
            self.email_body_template_edit.text(),
            self.email_interval_spin.value()
        )
        self.parser_thread.log_signal.connect(self.update_log)
        self.parser_thread.result_signal.connect(self.update_table)
        self.parser_thread.finished_signal.connect(self.parsing_finished)
        self.parser_thread.start()


    def stop_parsing(self):
        # Stop the parser
        if self.parser_thread:
            self.parser_thread.is_running = False
            self.stop_button.setEnabled(False)


    def update_log(self, message):
        # Update log area with message
        self.log_area.append(message)
        self.logger.info(message)


    def update_table(self, result):
        # Update results table with parsed data
        row = self.result_table.rowCount()
        self.result_table.insertRow(row)
        self.result_table.setItem(row, 0, QTableWidgetItem(result["inn"]))
        self.result_table.setItem(row, 1, QTableWidgetItem(str(result["status"])))
        self.result_table.setItem(row, 2, QTableWidgetItem(result["url"] or "N/A"))
        self.result_table.setItem(row, 3, QTableWidgetItem(str(result["region_id"])))

        try:
            self.db_service.insert_organization(
                result["inn"], result["status"], result["url"], result["region_id"]
            )
        except Exception as e:
            self.update_log(f"Error saving to database: {str(e)}")


    def parsing_finished(self):
        # Handle parsing completion
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.update_log("Parsing completed")


    def closeEvent(self, event):
        # Handle window close
        self.stop_parsing()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())