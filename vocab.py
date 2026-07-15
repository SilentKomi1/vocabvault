import streamlit as st
import sqlite3
from datetime import datetime
import requests
import random
import re

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect("vocab_vault.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vocabulary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT UNIQUE NOT NULL,
            definition TEXT NOT NULL,
            example TEXT,
            date_added TEXT NOT NULL,
            correct_attempts INTEGER DEFAULT 0,
            incorrect_attempts INTEGER DEFAULT 0,
            mastery_level INTEGER DEFAULT 0,
            part_of_speech TEXT DEFAULT 'Noun'
        )
    """)
    
    # Auto-migration for legacy databases
    try:
        cursor.execute("SELECT part_of_speech FROM vocabulary LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE vocabulary ADD COLUMN part_of_speech TEXT DEFAULT 'Noun'")
        conn.commit()
        
    conn.commit()
    conn.close()

init_db()

# --- HELPER FUNCTIONS ---
def get_db_connection():
    conn = sqlite3.connect("vocab_vault.db")
    conn.row_factory = sqlite3.Row
    return conn

def fetch_auto_definition(word):
    """Fetches definition, example, and part of speech from a free Public Dictionary API."""
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word.strip().lower()}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()[0]
            meanings = data.get("meanings", [])
            if meanings:
                part_of_speech = meanings[0].get("partOfSpeech", "Noun").capitalize()
                definition = meanings[0]["definitions"][0]["definition"]
                example = meanings[0]["definitions"][0].get("example", f"The word '{word}' is very useful.")
                return definition, example, part_of_speech
        return None, None, None
    except Exception:
        return None, None, None

def fetch_alternate_sentence(word):
    """Fetches an alternative AI/Dictionary-generated sentence for a specific word."""
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word.strip().lower()}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            meanings = response.json()[0].get("meanings", [])
            sentences = []
            for m in meanings:
                for d in m.get("definitions", []):
                    if d.get("example"):
                        sentences.append(d["example"])
            if sentences:
                return random.choice(sentences)
        # Fallback pseudo-generator if the specific API has no custom example sentence
        fallbacks = [
            f"It is important to understand how to use the word '{word}' in regular communication.",
            f"During the lecture, the professor explained the true significance of the concept of '{word}'.",
            f"She looked up the definition to ensure she was using '{word}' in the correct context."
        ]
        return random.choice(fallbacks)
    except Exception:
        return f"We need to find an appropriate context for using the word '{word}'."

# --- STREAMLIT UI ---
st.set_page_config(page_title="Vocab Vault", page_icon="📖", layout="wide")
st.title("📖 Vocab Vault: Personal Dictionary & Mastery Quiz")

# Sidebar navigation
menu = ["Add Vocabulary", "Catalog & Archive", "Quiz & Mastery Center"]
choice = st.sidebar.selectbox("Navigation Menu", menu)

# ---------------------------------------------------------
# PAGE 1: ADD VOCABULARY
# ---------------------------------------------------------
if choice == "Add Vocabulary":
    st.header("✨ Add a New Word")
    
    col1, col2 = st.columns(2)
    with col1:
        word_input = st.text_input("Enter Word", placeholder="e.g., Ephemeral").strip()
        date_input = st.date_input("Date Learned", datetime.today())
        
    with col2:
        generation_mode = st.radio(
            "Definition & Example Sentence Mode:",
            ("Auto-generate (using free online dictionary)", "Write my own custom text")
        )

    # Inputs for custom mode
    custom_def = ""
    custom_example = ""
    custom_pos = "Noun"
    
    if generation_mode == "Write my own custom text":
        col_sub1, col_sub2 = st.columns([1, 2])
        with col_sub1:
            custom_pos = st.selectbox("Part of Speech", ["Noun", "Adjective", "Verb", "Adverb", "Pronoun", "Preposition", "Conjunction", "Interjection"])
        custom_def = st.text_area("Your Definition")
        custom_example = st.text_area("Example Sentence using this word")

    if st.button("Save Word to Vault", use_container_width=True):
        if not word_input:
            st.warning("Please enter a word first!")
        else:
            definition, example, pos = "", "", ""
            success = True
            
            if generation_mode == "Auto-generate (using free online dictionary)":
                with st.spinner("Fetching details online..."):
                    definition, example, pos = fetch_auto_definition(word_input)
                if not definition:
                    st.error(f"Could not find definitions for '{word_input}' online. Please enter them manually.")
                    success = False
            else:
                definition = custom_def
                example = custom_example
                pos = custom_pos
                if not definition:
                    st.warning("You must provide at least a definition to save custom entries.")
                    success = False

            if success:
                conn = get_db_connection()
                try:
                    conn.execute(
                        "INSERT INTO vocabulary (word, definition, example, date_added, part_of_speech) VALUES (?, ?, ?, ?, ?)",
                        (word_input.capitalize(), definition, example, date_input.strftime("%Y-%m-%d"), pos)
                    )
                    conn.commit()
                    st.success(f"🎉 '{word_input.capitalize()}' ({pos}) added successfully!")
                except sqlite3.IntegrityError:
                    st.error("This word is already in your Vocab Vault!")
                finally:
                    conn.close()

# ---------------------------------------------------------
# PAGE 2: CATALOG & ARCHIVE
# ---------------------------------------------------------
elif choice == "Catalog & Archive":
    st.header("🗃️ Your Personal Vocabulary Catalog")
    
    conn = get_db_connection()
    words_data = conn.execute("SELECT * FROM vocabulary ORDER BY date_added DESC").fetchall()
    conn.close()

    if not words_data:
        st.info("Your vault is empty! Head to 'Add Vocabulary' to add your first word.")
    else:
        col_f1, col_f2, col_f3 = st.columns(3)
        
        with col_f1:
            search_meaning = st.text_input("🔍 Search by Meaning / Keyword", placeholder="e.g., innocent").strip().lower()
            
        with col_f2:
            all_pos_options = sorted(list(set([row["part_of_speech"] for row in words_data])))
            all_pos_options.insert(0, "All Parts of Speech")
            selected_pos = st.selectbox("Filter by Part of Speech:", all_pos_options)
            
        with col_f3:
            all_dates = sorted(list(set([row["date_added"] for row in words_data])), reverse=True)
            all_dates.insert(0, "All Dates")
            selected_date = st.selectbox("Filter by Date Added:", all_dates)

        # Multi-stage filtering logic
        filtered_words = []
        for row in words_data:
            date_match = (selected_date == "All Dates" or row["date_added"] == selected_date)
            pos_match = (selected_pos == "All Parts of Speech" or row["part_of_speech"] == selected_pos)
            meaning_match = True
            if search_meaning:
                meaning_match = (search_meaning in row["definition"].lower() or search_meaning in row["word"].lower())
            
            if date_match and pos_match and meaning_match:
                filtered_words.append(row)

        st.write(f"Showing **{len(filtered_words)}** matching words:")

        for item in filtered_words:
            with st.expander(f"📌 **{item['word']}** *({item['part_of_speech']})* | Added: {item['date_added']} | Mastery Level: {item['mastery_level']}"):
                col_left, col_right = st.columns([3, 1])
                
                with col_left:
                    new_pos = st.selectbox("Part of Speech", ["Noun", "Adjective", "Verb", "Adverb", "Pronoun", "Preposition", "Conjunction", "Interjection"], index=["Noun", "Adjective", "Verb", "Adverb", "Pronoun", "Preposition", "Conjunction", "Interjection"].index(item['part_of_speech']) if item['part_of_speech'] in ["Noun", "Adjective", "Verb", "Adverb", "Pronoun", "Preposition", "Conjunction", "Interjection"] else 0, key=f"pos_{item['id']}")
                    new_def = st.text_area("Definition", value=item['definition'], key=f"def_{item['id']}")
                    new_ex = st.text_area("Example Sentence", value=item['example'], key=f"ex_{item['id']}")
                    
                    col_buttons = st.columns(2)
                    with col_buttons[0]:
                        if st.button("💾 Save Changes", key=f"save_{item['id']}"):
                            conn = get_db_connection()
                            conn.execute(
                                "UPDATE vocabulary SET definition = ?, example = ?, part_of_speech = ? WHERE id = ?",
                                (new_def, new_ex, new_pos, item['id'])
                            )
                            conn.commit()
                            conn.close()
                            st.success("Changes saved! Refreshing...")
                            st.rerun()
                    with col_buttons[1]:
                        if st.button("🗑️ Delete Word", key=f"del_{item['id']}"):
                            conn = get_db_connection()
                            conn.execute("DELETE FROM vocabulary WHERE id = ?", (item['id'],))
                            conn.commit()
                            conn.close()
                            st.warning("Word deleted.")
                            st.rerun()
                
                with col_right:
                    st.metric("Correct Answers", item['correct_attempts'])
                    st.metric("Wrong Answers", item['incorrect_attempts'])

# ---------------------------------------------------------
# PAGE 3: QUIZ & MASTERY CENTER
# ---------------------------------------------------------
elif choice == "Quiz & Mastery Center":
    st.header("🧠 Mastery Quizzes")

    conn = get_db_connection()
    all_words = conn.execute("SELECT * FROM vocabulary").fetchall()
    conn.close()

    if len(all_words) < 3:
        st.warning("Add at least 3 words to your vault to unlock quizzes.")
    else:
        # Quiz Settings
        col_set1, col_set2 = st.columns(2)
        with col_set1:
            quiz_filter = st.selectbox(
                "Choose Quiz Focus:",
                ["All Words", "Weak Words Only (Mastery Level less than 2)"]
            )
            
            quiz_type = st.radio(
                "Select Quiz Format:",
                ["Flashcards", "Definition Matching", "Fill-in-the-Blank Sentences"]
            )
        
        with col_set2:
            # ONLY show sentence source selector if Fill-in-the-Blank is chosen
            sentence_source = "Vault"
            if quiz_type == "Fill-in-the-Blank Sentences":
                sentence_source = st.radio(
                    "Sentence Source:",
                    ["Use Sentences Saved in Vault", "Auto-Generate Fresh Sentence (AI / Web Dictionary)"],
                    help="Choose whether to practice with sentences you added or generate brand-new ones dynamically!"
                )

        # Filter the quiz pool
        if "Weak Words" in quiz_filter:
            pool = [w for w in all_words if w['mastery_level'] < 2]
            if not pool:
                st.success("You've mastered everything! Showing all words instead.")
                pool = all_words
        else:
            pool = all_words

        st.write(f"Current Quiz Pool size: **{len(pool)}** words.")

        # Initialize session state for quiz
        if 'quiz_word' not in st.session_state or st.button("🔄 Generate New Question"):
            st.session_state.quiz_word = random.choice(pool)
            # Fetch distractors for matching
            distractors = [w for w in all_words if w['word'] != st.session_state.quiz_word['word']]
            st.session_state.options = random.sample(distractors, min(len(distractors), 3)) + [st.session_state.quiz_word]
            random.shuffle(st.session_state.options)
            st.session_state.answered = False
            st.session_state.feedback = ""
            # Prepare sentence based on choice
            word = st.session_state.quiz_word['word']
            if sentence_source == "Auto-Generate Fresh Sentence (AI / Web Dictionary)":
                with st.spinner("Generating fresh contextual sentence..."):
                    st.session_state.active_sentence = fetch_alternate_sentence(word)
            else:
                st.session_state.active_sentence = st.session_state.quiz_word['example']

        current_q = st.session_state.quiz_word

        # --- MODE 1: FLASHCARDS ---
        if quiz_type == "Flashcards":
            st.subheader("💡 Flashcard Mode")
            st.info("Read the word, guess the definition, and flip to self-evaluate!")
            
            card_container = st.container(border=True)
            with card_container:
                st.markdown(f"<h1 style='text-align: center;'>{current_q['word']} <span style='font-size: 18px; font-weight: normal; color: gray;'>({current_q['part_of_speech']})</span></h1>", unsafe_allow_html=True)
                
                if st.checkbox("🔍 Reveal Definition & Sentence"):
                    st.write(f"**Definition:** {current_q['definition']}")
                    st.write(f"*Example:* {current_q['example']}")
                    
                    st.divider()
                    st.write("How did you do?")
                    col_correct, col_wrong = st.columns(2)
                    
                    if col_correct.button("👍 Got it Right!", use_container_width=True):
                        conn = get_db_connection()
                        conn.execute("UPDATE vocabulary SET correct_attempts = correct_attempts + 1, mastery_level = mastery_level + 1 WHERE id = ?", (current_q['id'],))
                        conn.commit()
                        conn.close()
                        st.success("Mastery Increased!")
                        st.rerun()
                        
                    if col_wrong.button("👎 Got it Wrong", use_container_width=True):
                        conn = get_db_connection()
                        conn.execute("UPDATE vocabulary SET incorrect_attempts = incorrect_attempts + 1, mastery_level = CASE WHEN mastery_level > 0 THEN mastery_level - 1 ELSE 0 END WHERE id = ?", (current_q['id'],))
                        conn.commit()
                        conn.close()
                        st.error("Mastery Decreased. Added to weak words review!")
                        st.rerun()

        # --- MODE 2: MATCHING ---
        elif quiz_type == "Definition Matching":
            st.subheader("🔗 Definition Matching")
            st.write(f"Which of the following defines the {current_q['part_of_speech'].lower()}: **{current_q['word']}**?")

            options_dict = {opt['definition']: opt['word'] for opt in st.session_state.options}
            user_choice = st.radio("Choose the correct definition:", list(options_dict.keys()))

            if st.button("Submit Answer") and not st.session_state.answered:
                st.session_state.answered = True
                correct_word = options_dict[user_choice]
                
                conn = get_db_connection()
                if correct_word == current_q['word']:
                    st.session_state.feedback = "✅ Correct! Well done."
                    conn.execute("UPDATE vocabulary SET correct_attempts = correct_attempts + 1, mastery_level = mastery_level + 1 WHERE id = ?", (current_q['id'],))
                else:
                    st.session_state.feedback = f"❌ Incorrect. The correct answer was: '{current_q['word']}'."
                    conn.execute("UPDATE vocabulary SET incorrect_attempts = incorrect_attempts + 1, mastery_level = CASE WHEN mastery_level > 0 THEN mastery_level - 1 ELSE 0 END WHERE id = ?", (current_q['id'],))
                conn.commit()
                conn.close()
            
            if st.session_state.feedback:
                st.write(st.session_state.feedback)

        # --- MODE 3: FILL IN THE BLANK ---
        elif quiz_type == "Fill-in-the-Blank Sentences":
            st.subheader("📝 Context Fill-in-the-Blank")
            
            sentence = st.session_state.get('active_sentence', '')
            word = current_q['word']
            
            if not sentence or word.lower() not in sentence.lower():
                st.warning(f"No valid sentence containing '{word}' was found in your selected source.")
                st.info("Try switching your 'Sentence Source' toggle to 'Auto-Generate' or generate a new question.")
            else:
                # Blank out the word (case-insensitive)
                blanked_sentence = re.sub(re.escape(word), "_______", sentence, flags=re.IGNORECASE)
                
                difficulty = "Medium" if len(word) > 7 else "Easy"
                st.caption(f"Difficulty Level: {difficulty} | Clue: {current_q['part_of_speech']}")
                
                # Render the blanked sentence
                st.markdown(f"### *\"{blanked_sentence}\"*")
                
                # --- HINT OPTION ---
                with st.expander("💡 Need a Hint?"):
                    st.write(f"**Definition:** {current_q['definition']}")
                
                user_guess = st.text_input("Type the missing word:").strip().lower()

                if st.button("Submit Guess") and not st.session_state.answered:
                    st.session_state.answered = True
                    conn = get_db_connection()
                    if user_guess == word.lower():
                        st.session_state.feedback = "🎉 Spot on! Correct."
                        conn.execute("UPDATE vocabulary SET correct_attempts = correct_attempts + 1, mastery_level = mastery_level + 1 WHERE id = ?", (current_q['id'],))
                    else:
                        st.session_state.feedback = f"❌ Incorrect. The correct word was '{word}'."
                        conn.execute("UPDATE vocabulary SET incorrect_attempts = incorrect_attempts + 1, mastery_level = CASE WHEN mastery_level > 0 THEN mastery_level - 1 ELSE 0 END WHERE id = ?", (current_q['id'],))
                    conn.commit()
                    conn.close()

                if st.session_state.feedback:
                    st.write(st.session_state.feedback)
