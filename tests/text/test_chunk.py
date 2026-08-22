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
