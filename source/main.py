import sys
import asyncio
import csv
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QTableWidget, QTableWidgetItem,
    QComboBox, QLabel, QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from handlers.datetime_handler import current_time
from handlers.logging_handler import setup_logger
from services.bankrupt_parser_service import BankruptParserService
from services.database_service import DatabaseService
from bs4 import BeautifulSoup


class ParserThread(QThread):
    log_signal = pyqtSignal(str)
    result_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal()


    def __init__(self, parser: BankruptParserService, region_id: int):
        super().__init__()
        self.parser = parser
        self.region_id = region_id
        self.is_running = True


    def run(self):
        asyncio.run(self.parse())


    async def parse(self):
        try:
            url = f"https://bankrot.fedresurs.ru/bankrupts?regionId={self.region_id}&isActiveLegalCase=true&offset=0&limit=100"
            page = await self.parser.load_page(url)

            await page.wait_for_selector("app-bankrupt-result-card-company")
            cards = await page.locator("app-bankrupt-result-card-company").all()
            self.log_signal.emit(f"Cards found: {len(cards)}")

            for i, card in enumerate(cards):
                if not self.is_running:
                    self.log_signal.emit("Parser stopped")
                    break

                try:
                    card_soup = BeautifulSoup(await card.inner_html(), "html.parser")
                    result = await self.parser.parse_card(page, card_soup, card)
                    if result:
                        self.result_signal.emit(result)
                        self.log_signal.emit(f"Card proceed {i}: INN={result['inn']}, URL={result['url']}")
                except Exception as e:
                    self.log_signal.emit(f"Error while card processing {i}: {str(e)}")

        except Exception as e:
            self.log_signal.emit(f"Parcing error: {str(e)}")
        finally:
            # if page:
            #     await page.close()
            self.finished_signal.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bankrupt Parser")
        self.setGeometry(100, 100, 1200, 600)
        self.parser_thread = None

        # Services initialization
        self.db_service = DatabaseService()
        self.parser_service = BankruptParserService()

        # Logger setup
        self.logger = setup_logger("App", "Logs", f"App_Log_{current_time()}.log")

        # UI initialization
        self.init_ui()


    def init_ui(self):
        # Main widet  and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Control Panel
        control_layout = QHBoxLayout()
        main_layout.addLayout(control_layout)

        # Region Selection
        self.region_combo = QComboBox()
        self.region_combo.addItems([f"Регион {i}" for i in range(1, 10)])  # Пример регионов
        control_layout.addWidget(QLabel("Регион:"))
        control_layout.addWidget(self.region_combo)

        # Buttons
        self.start_button = QPushButton("Запустить парсер")
        self.start_button.clicked.connect(self.start_parsing)
        control_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("Остановить")
        self.stop_button.clicked.connect(self.stop_parsing)
        self.stop_button.setEnabled(False)
        control_layout.addWidget(self.stop_button)

        self.export_button = QPushButton("Экспорт в CSV")
        self.export_button.clicked.connect(self.export_to_csv)
        control_layout.addWidget(self.export_button)

        # Таблица результатов
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(3)
        self.result_table.setHorizontalHeaderLabels(["INN", "Status", "URL"])
        self.result_table.setRowCount(0)
        self.result_table.setColumnWidth(0, 150)
        self.result_table.setColumnWidth(1, 100)
        self.result_table.setColumnWidth(2, 600)
        main_layout.addWidget(self.result_table)

        # Поле логов
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setFont(QFont("Courier", 10))
        main_layout.addWidget(self.log_area)


    def start_parsing(self):
        region_id = self.region_combo.currentIndex() + 1
        self.logger.info(f"Starting parsing for region {region_id}")

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.result_table.setRowCount(0)

        self.parser_thread = ParserThread(self.parser_service, region_id)
        self.parser_thread.log_signal.connect(self.update_log)
        self.parser_thread.result_signal.connect(self.update_table)
        self.parser_thread.finished_signal.connect(self.parsing_finished)
        self.parser_thread.start()


    def stop_parsing(self):
        if self.parser_thread:
            self.parser_thread.is_running = False
            self.stop_button.setEnabled(False)


    def update_log(self, message):
        self.log_area.append(message)
        self.logger.info(message)


    def update_table(self, result):
        row = self.result_table.rowCount()
        self.result_table.insertRow(row)
        self.result_table.setItem(row, 0, QTableWidgetItem(result["inn"]))
        self.result_table.setItem(row, 1, QTableWidgetItem(str(result["status"])))
        self.result_table.setItem(row, 2, QTableWidgetItem(result["url"] or "N/A"))

        # Сохраняем в базу
        try:
            region_id = self.region_combo.currentIndex() + 1
            self.db_service.insert_organization(
                result["inn"], result["status"], result["url"], region_id
            )
        except Exception as e:
            self.update_log(f"Ошибка сохранения в базу: {str(e)}")


    def parsing_finished(self):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.update_log("Парсинг завершен")


    def export_to_csv(self):
        region_id = self.region_combo.currentIndex() + 1
        organizations = self.db_service.get_organizations_by_region(region_id)

        if not organizations:
            QMessageBox.warning(self, "Экспорт", "Нет данных для экспорта")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить CSV", "", "CSV Files (*.csv)")
        if file_path:
            try:
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["INN", "Status", "URL"])
                    writer.writerows(organizations)
                QMessageBox.information(self, "Экспорт", "Данные успешно экспортированы")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать: {str(e)}")


    def closeEvent(self, event):
        self.stop_parsing()
        # if self.parser_service.browser:
        #     asyncio.run(self.parser_service.browser.close())
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())