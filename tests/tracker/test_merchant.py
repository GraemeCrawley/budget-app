from tracker.merchant import PREVIOUS_KEYS, merchant_key


def test_generic_prefixes_and_reference_tokens_are_removed():
    assert merchant_key("RETAIL PURCHASE 000123456 Corner Cafe") == "CORNER CAFE"
    assert merchant_key("Point of Sale  CORNER CAFE #4417") == "CORNER CAFE"
    assert merchant_key("corner cafe *AB12 [3]") == "CORNER CAFE"


def test_two_merchants_behind_the_same_prefix_get_different_keys():
    assert merchant_key("RETAIL PURCHASE 111122223 BOOK BARN") != merchant_key("RETAIL PURCHASE 111122224 CORNER CAFE")


def test_key_is_at_most_20_characters_and_can_be_empty():
    assert merchant_key("A VERY LONG MERCHANT NAME INDEED LTD") == "A VERY LONG MERCHANT"
    assert merchant_key("E-TRANSFER 00012345678") == ""


def test_a_processor_prefix_keeps_the_merchant_name_after_its_star():
    spotify, books = merchant_key("PAYPAL *SPOTIFY"), merchant_key("PAYPAL *BOOKBARN")
    assert spotify != books
    assert "SPOTIFY" in spotify and "BOOKBARN" in books
    assert merchant_key("SQ *CORNER CAFE") != merchant_key("SQ *OTHER CAFE")


def test_a_starred_reference_with_a_digit_is_still_removed():
    assert merchant_key("AMZN Mktp CA*1A2B3C") == "AMZN MKTP CA"


def test_a_reference_removed_after_a_hash_leaves_no_lone_punctuation():
    assert merchant_key("FUELCO # 44172 FUELC OAKTOWN") == "FUELCO FUELC OAKTOWN"
    assert merchant_key("FUELCO - 44172 / FUELC") == "FUELCO FUELC"
    assert all(any(ch.isalnum() for ch in tok) for tok in merchant_key("FUELCO # 44172 * FUELC").split())


def test_a_lone_ampersand_between_words_is_dropped_by_design():
    # accepted: "A & W" becomes "A W"; an ampersand inside a word ("AT&T") is kept
    assert merchant_key("A & W") == "A W"
    assert merchant_key("AT&T PAYMENT") == "AT&T PAYMENT"


def test_leading_and_trailing_punctuation_is_stripped():
    assert merchant_key("-- CORNER CAFE --") == "CORNER CAFE"
    assert merchant_key("# 12345 -") == ""


def test_the_earlier_keys_are_frozen():
    first, second = PREVIOUS_KEYS
    assert first("FUELCO # 44172 FUELC TORONTO ON") == "FUELCO # FUELC TORON"
    assert first("CORNER CAFE #4417") == "CORNER CAFE"
    assert second("FUELCO # 44172 FUELC TORONTO ON") == "FUELCO FUELC TORONTO"
    assert second("1100 SIDE ST. WEST TORONTO") == "SIDE ST. WEST TORONT"


def test_the_place_a_bank_appends_is_dropped_however_often_it_repeats():
    assert merchant_key("GREEN GROCER TORONTO") == "GREEN GROCER"
    assert merchant_key("GREEN GROCER TORONTO TORONTO ON") == "GREEN GROCER"
    assert merchant_key("GREEN GROCER NORTH YORK") == "GREEN GROCER"
    assert merchant_key("GREEN GROCER ST. CATHARINES") == "GREEN GROCER"


def test_a_place_that_is_the_whole_name_or_follows_of_is_kept():
    assert merchant_key("TORONTO") == "TORONTO"
    assert merchant_key("TORONTO TORONTO") == "TORONTO"
    assert merchant_key("CITY OF TORONTO") == "CITY OF TORONTO"
    assert merchant_key("COME ON") == "COME ON"


def test_a_leading_street_number_or_company_number_is_kept():
    assert merchant_key("1100 Side St. West Toronto") == "1100 SIDE ST. WEST"
    assert merchant_key("1234567 Ontario Lt") == "1234567 ONTARIO LT"
    assert merchant_key("1100 TORONTO") == "1100 TORONTO"


def test_a_leading_reference_is_still_removed():
    assert merchant_key("000000123456 CORNER CAFE") == "CORNER CAFE"
    assert merchant_key("000123456 CORNER CAFE") == "CORNER CAFE"
    assert merchant_key("RETAIL PURCHASE 4417 CORNER CAFE") == "CORNER CAFE"
    assert merchant_key("INTERNET TRANSFER 000000123456 CORNER CAFE") == "CORNER CAFE"


def test_a_long_name_is_cut_on_a_word_boundary():
    assert merchant_key("GREEN GROCER HARBOUR VILLAGE") == "GREEN GROCER HARBOUR"
    assert merchant_key("GROCER HARBOUR VILLAGE MARKET") == "GROCER HARBOUR"
    assert merchant_key("ABCDEFGHIJKLMNOPQRSTUVWXYZ") == "ABCDEFGHIJKLMNOPQRST"
