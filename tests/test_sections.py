from crlib.extract import extract_text
from crlib.sections import split_sections


def test_split_fixture(fixtures):
    secs = split_sections(extract_text(fixtures / "msa_v1.txt"))
    assert secs[0].title == "Preamble" and "Example Corp" in secs[0].text
    assert [s.number for s in secs[1:]] == [str(i) for i in range(1, 10)]
    assert secs[2].title == "Term and Renewal"
    assert "sixty (60) days" in secs[2].text


def test_heading_variants():
    text = ("Article IV. Warranties\nThe goods are new.\n"
            "Section 5 Governing Law\nThe law of Exampleland applies.\n"
            "5.1 Disputes. Disputes go to mediation first.\n"
            "30 days after delivery the warranty starts.\n")
    secs = split_sections(text)
    assert [(s.number, s.title, s.level) for s in secs] == [
        ("IV", "Warranties", 1), ("5", "Governing Law", 1), ("5.1", "Disputes", 2)]
    assert secs[2].text.startswith("Disputes go to mediation first.")
    assert "30 days after delivery" in secs[2].text  # not split as heading


def test_long_numbered_line_has_no_title():
    secs = split_sections("2.3 The Supplier shall maintain insurance of not less than the amount set out in Schedule C at all times.\n")
    assert secs[0].number == "2.3" and secs[0].title == ""
    assert secs[0].text.startswith("The Supplier shall maintain")
