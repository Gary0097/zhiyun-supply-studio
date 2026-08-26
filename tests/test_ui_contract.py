from pathlib import Path
import unittest


class UiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (Path(__file__).parents[1] / "ui" / "index.js").read_text(encoding="utf-8")

    def test_guided_gui_and_agent_dock_are_present(self) -> None:
        self.assertIn("问 Agent", self.source)
        self.assertIn("数据来源", self.source)
        self.assertIn("模拟数据已明确标注", self.source)
        self.assertIn("待审阅工件", self.source)

    def test_ui_does_not_render_raw_json_as_the_business_result(self) -> None:
        self.assertNotIn("JSON.stringify(result, null, 2)", self.source)

    def test_excel_csv_import_is_available_on_editable_tables(self) -> None:
        self.assertIn("导入 Excel/CSV", self.source)
        self.assertIn("/zhiyun-data-core/parse", self.source)
        self.assertIn("下载导入模板", self.source)
        self.assertIn("rowsFromParsed", self.source)


if __name__ == "__main__":
    unittest.main()
