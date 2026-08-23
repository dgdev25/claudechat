from claudechat.text.chunk import SentenceChunker


def test_emits_on_sentence_terminator():
    c = SentenceChunker()
    assert c.feed("Hello there. ") == ["Hello there."]


def test_does_not_split_on_abbreviation():
    c = SentenceChunker()
    out = c.feed("It costs 3.5 units approx. and no more. ")
    assert out == ["It costs 3.5 units approx. and no more."]


def test_first_chunk_released_early_on_comma():
    c = SentenceChunker()
    out = c.feed("Yes I can help with that, and here is why it matters. ")
    assert out[0] == "Yes I can help with that,"


def test_later_chunks_do_not_split_on_comma():
    c = SentenceChunker()
    c.feed("First one here. ")
    out = c.feed("Second, with a comma, keeps going. ")
    assert out == ["Second, with a comma, keeps going."]


def test_flush_emits_trailing_partial():
    c = SentenceChunker()
    c.feed("Complete one. ")
    c.feed("Dangling text")
    assert c.flush() == ["Dangling text"]


def test_fragmented_input_reassembles():
    c = SentenceChunker()
    out = c.feed("Hel") + c.feed("lo wor") + c.feed("ld. ")
    assert out == ["Hello world."]


def test_first_chunk_on_word_count_limit_ends_with_comma():
    # When word-count path releases the first chunk, it should end with a comma
    # for proper Kokoro intonation (continuing, not final)
    c = SentenceChunker(first_chunk_min_chars=5, first_chunk_max_words=5)
    # Feed text that will exceed word limit before hitting a terminator
    # 6 words at the start, word-count path kicks in and adds comma
    out = c.feed("one two three four five six and more")
    assert len(out) == 1
    assert out[0] == "one two three four five,"
