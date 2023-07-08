import logging
import os

import dotenv
import firebase_admin
import kivy.properties as kvprops
import openai
import pyrebase
from kivy.storage.jsonstore import JsonStore
from firebase_admin import auth, credentials
from kivy.lang import Builder
from kivy.metrics import dp
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.list import IconRightWidget, OneLineAvatarIconListItem
from kivymd.uix.screenmanager import MDScreenManager

dotenv.load_dotenv()

# --------------------------------------------------------------------------------

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
FIREBASE_WEB_API_KEY = os.getenv("FIREBASE_WEB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_SECRET = os.getenv("DATABASE_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
APP_ID = os.getenv("APP_ID")
SENDER_ID = os.getenv("SENDER_ID")

# --------------------------------------------------------------------------------

INSTRUCTIONS = """<<PUT THE PROMPT HERE>>"""
TEMPERATURE = 0.5
MAX_TOKENS = 500
FREQUENCY_PENALTY = 0
PRESENCE_PENALTY = 0.6
MAX_CONTEXT_QUESTIONS = 10  # Limits how many questions we include in the prompt

# ------------------------------------------------------------------------------

openai.api_key = OPENAI_API_KEY

config = {
    "apiKey": FIREBASE_WEB_API_KEY,
    "authDomain": "dataai-dev.firebaseapp.com",
    "projectId": "dataai-dev",
    "storageBucket": "dataai-dev.appspot.com",
    "messagingSenderId": SENDER_ID,
    "databaseURL": DATABASE_URL,
    "appId": APP_ID,
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

cred = credentials.Certificate(GOOGLE_APPLICATION_CREDENTIALS)
firebase_admin.initialize_app(cred)

firebase = pyrebase.initialize_app(config)
auth_firebase = firebase.auth()
db = firebase.database()


class ChatBubble(MDBoxLayout):
    halign = kvprops.StringProperty()
    btype = kvprops.StringProperty()
    full_text = kvprops.StringProperty()


class ChatLayout(MDBoxLayout):
    chat_id = kvprops.NumericProperty()


class MainApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.read_more_button = None
        self.cb_box = None
        self.camera_screen = None
        self.cb_label = None
        self.login_check = None
        self.send_layout = None
        self.chat_layout = None
        self.nav_drawer = None
        self.home_screen = None
        self.signup_screen = None
        self.login_screen = None
        self.sm = None
        self.prev_q_a = []
        self.dialog = None
        self.dialog_btn = None
        self.cb_parent = None
        self.user = None
        self.chat_bubbles = []
        self.response = ""
        self.chat_count = 0
        self.title = ""
        self.chat_layouts = []
        self.chat_sessions = []
        self.store = JsonStore('credentials.json')  # JsonStore for storing credentials

    def build(self):
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "Indigo"
        self.theme_cls.material_style = "M3"

        return self.load_login_screen()

    def load_login_screen(self):
        """
        Loads login screen.
        :return: MDScreenManager
        """
        Builder.load_file("uix/widgets/custom_widgets.kv")
        self.login_screen = Builder.load_file("uix/screens/login_screen.kv")
        self.sm = MDScreenManager()
        self.sm.add_widget(self.login_screen)
        self.sm.current = "login"
        return self.sm

    def load_signup_screen(self):
        """
        Loads sign up screen.
        :return: None
        """
        self.signup_screen = Builder.load_file("uix/screens/signup_screen.kv")
        self.sm.add_widget(self.signup_screen)

    def load_home_screen(self):
        """
        Loads home screen.
        :return: None
        """
        self.home_screen = Builder.load_file("uix/screens/home_screen.kv")
        self.nav_drawer = Builder.load_file("uix/widgets/nav_drawer.kv")
        self.chat_layout = Builder.load_file("uix/widgets/chat_layout.kv")
        self.send_layout = Builder.load_file("uix/widgets/send_layout.kv")

        self.home_screen.add_widget(self.nav_drawer, index=0)
        self.home_screen.add_widget(self.chat_layout, index=2)
        self.home_screen.add_widget(self.send_layout, index=1)
        self.sm.add_widget(self.home_screen)

    def load_camera_screen(self):
        """
        Loads camera screen.
        :return: None
        """
        self.camera_screen = Builder.load_file("uix/screens/camera_screen.kv")
        self.sm.add_widget(self.camera_screen)

    def on_start(self):
        self.load_signup_screen()
        self.load_home_screen()
        self.chat_layouts.append(self.chat_layout)
        if "idToken" in self.store:
            token = self.store["idToken"]["token"]
            print(token)
            login_email = auth.verify_id_token(token)["email"]
            login_password = db.child("users").child(self.replace_str(login_email, "to_db"))\
                               .child("password").get().val()
            self.login_screen.ids.login_email.text = login_email
            self.login_screen.ids.login_password.text = login_password
            self.login(auto_login=True)

    def on_stop(self):
        return super().on_stop()

    @staticmethod
    def clear_text(*fields):
        """
        Clears texts of given text fields.
        :param fields:
        :return: None
        """
        for field in fields:
            field.text = ""

    def switch_screen(self, screen_name: str):
        """
        Switches to screen by given screen name.
        :param screen_name:
        :return: None
        """
        if screen_name == "camera":
            self.load_camera_screen()

        self.sm.current = screen_name

    @staticmethod
    def input_limit(obj, max_length: int, _type: str):
        """
        Limits the inputs of login, password and username text fields.
        :param obj:
        :param max_length:
        :param _type:
        :return: None
        """
        if len(obj.text) > max_length:
            obj.text = obj.text[:max_length]
        replacement_chars = {
            "u": "/\\*.,_?|:;`´¨~@&½$%><\"'[]}{+#£!^\t ",
            "e": "/\\*,?|:;`´¨~&½$%><\"'[]}{+#£!^\t ",
            "p": "/\\|:;`´¨½$%><\"'[]}{#£^\t ",
        }
        if _type in replacement_chars:
            obj.text = "".join(c for c in obj.text if c not in replacement_chars[_type])

    def login(self, auto_login=False):
        """
        Perform login action.
        :param auto_login:
        :return: Any
        """
        login_email = self.login_screen.ids.login_email.text
        login_password = self.login_screen.ids.login_password.text

        db_user = db.child("users").child(self.replace_str(login_email, "to_db")).get()
        db_email = db_user.val()["email"]
        db_password = db_user.val()["password"]
        db_username = db_user.val()["username"]

        try:
            if login_email == db_email and login_password == db_password:
                self.user = auth_firebase.sign_in_with_email_and_password(
                    login_email, login_password
                )
                self.login_check = True
                self.switch_screen("home")
                if not auto_login:
                    self.dialog_open(
                        "Logged In",
                        f'Successfully logged in as "{db_username}".',
                        "OK",
                    )

                self.get_chat_log()

                self.nav_drawer.ids.user_label.text = self.user["email"]

                self.store.put("idToken", token=self.user["idToken"])
                self.user["refreshToken"] = auth_firebase.refresh(self.user["refreshToken"])["refreshToken"]
            else:
                raise Exception("Invalid email or password")
        except Exception as e:
            self.dialog_open("Error", f"{e}", "Retry")
            self.clear_text(
                self.login_screen.ids.login_email,
                self.login_screen.ids.login_password,
            )

    def sign_up(self):
        """
        Perform sign up action.
        :return: None
        """
        signup_screen = self.signup_screen
        signup_username = signup_screen.ids.signup_username.text
        signup_email = signup_screen.ids.signup_email.text
        signup_password = signup_screen.ids.signup_password.text

        if not signup_email or not signup_password or not signup_username:
            self.dialog_open("Error", "Invalid input.", "Retry")
        else:
            try:
                users = db.child("users").get().val()
                if users is not None:
                    for user in users.values():
                        if user["username"] == signup_username:
                            self.dialog_open(
                                "Error", "Username already exists.", "Retry"
                            )
                            return

                auth_firebase.create_user_with_email_and_password(
                    signup_email, signup_password
                )
                db_username = self.replace_str(signup_email, "to_db")
                db.child("users").child(db_username).child("username").set(
                    signup_username
                )
                db.child("users").child(db_username).child("email").set(signup_email)
                db.child("users").child(db_username).child("password").set(
                    signup_password
                )
                self.dialog_open("Success", "Successfully created account.", "OK")
                self.switch_screen("login")
            except Exception as e:
                error_messages = {
                    auth.EmailAlreadyExistsError: "The user with the provided email already exists.",
                    auth.UidAlreadyExistsError: "The user with the provided username already exists.",
                }
                error_message = error_messages.get(type(e), str(e))
                self.dialog_open("Error", error_message, "Retry")
                self.clear_text(
                    signup_screen.ids.signup_username,
                    signup_screen.ids.signup_email,
                    signup_screen.ids.signup_password,
                )

    def create_dialog(self):
        """
        Create dialog window.
        :return: None
        """
        if not self.dialog:
            self.dialog_btn = MDRaisedButton(
                text="", on_release=self.dialog_dismiss, elevation=2
            )
            self.dialog = MDDialog(buttons=[self.dialog_btn], elevation=2)

    def dialog_open(self, title_text: str, dg_text: str, btn_text: str):
        """
        Opens the dialog window.
        :param title_text:
        :param dg_text:
        :param btn_text:
        :return: None
        """
        self.create_dialog()

        self.dialog.title = title_text
        self.dialog.text = dg_text
        self.dialog_btn.text = btn_text

        self.dialog.open()

    def dialog_dismiss(self, obj):
        """
        Dismisses the dialog window.
        :param obj:
        :return: None
        """
        self.dialog.dismiss(obj)

    @staticmethod
    def get_response(instructions: str, previous_questions_and_answers: list, new_question: str):
        """
        Creates a completion with given parameters and prompt.
        :param instructions: Instructions that will be given to chatbot
        :param previous_questions_and_answers:
        :param new_question:
        :return: str
        """
        messages = [
            {"role": "system", "content": instructions},
        ]
        for question, answer in previous_questions_and_answers[-MAX_CONTEXT_QUESTIONS:]:
            messages.append({"role": "user", "content": question})
            messages.append({"role": "assistant", "content": answer})
        messages.append({"role": "user", "content": new_question})

        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            top_p=1,
            frequency_penalty=FREQUENCY_PENALTY,
            presence_penalty=PRESENCE_PENALTY,
        )
        return str(completion.choices[0].message.content)

    @staticmethod
    def get_moderation(question: str):
        """
        Checks moderation of the given prompt.
        :param question:
        :return: Optional[list[str]]
        """
        errors = {
            "hate": "Content that expresses, incites, or promotes hate based on race, gender, ethnicity, religion, "
                    "nationality, sexual orientation, disability status, or caste.",
            "hate/threatening": "Hateful content that also includes violence or serious harm towards the targeted "
                                "group.",
            "self-harm": "Content that promotes, encourages, or depicts acts of self-harm, such as suicide, cutting, "
                         "and eating disorders.",
            "sexual": "Content meant to arouse sexual excitement, such as the description of sexual activity, "
                      "or that promotes sexual services (excluding sex education and wellness).",
            "sexual/minors": "Sexual content that includes an individual who is under 18 years old.",
            "violence": "Content that promotes or glorifies violence or celebrates the suffering or humiliation of "
                        "others.",
            "violence/graphic": "Violent content that depicts death, violence, or serious physical injury in extreme "
                                "graphic detail.",
        }

        # if "failure_keyword" in question.lower():
        #     return ["Failed moderation check for testing purposes."]

        response = openai.Moderation.create(input=question)
        if response.results[0].flagged:
            result = [
                "Failed moderation check: " + error
                for category, error in errors.items()
                if response.results[0].categories[category]
            ]
            return result
        return None

    def completion(self):
        """
        Gets completion results and performs session tasks.
        :return: str
        """
        try:
            new_question = self.cb_label.text
            errors = self.get_moderation(new_question)
            if errors:
                raise Exception(errors)
            self.response = self.get_response(INSTRUCTIONS, self.prev_q_a, new_question)
            if len(self.prev_q_a) == 0:
                self.title = self.generate_title(new_question, self.response)

            item_id = f"item_{self.chat_layout.chat_id}"

            for i, (session_item_id, prev_q_a) in enumerate(self.chat_sessions):
                if session_item_id == item_id:
                    self.chat_sessions[i] = (
                        item_id,
                        prev_q_a + [(new_question, self.response)],
                    )
                    self.prev_q_a = prev_q_a + [(new_question, self.response)]
                    break
            else:
                self.chat_sessions.append((item_id, [(new_question, self.response)]))
                self.prev_q_a = [(new_question, self.response)]

            return self.response
        except Exception as e:
            e = str(e).removeprefix("[").removesuffix("]").replace("'", "")
            self.dialog_open("Error", e, "Retry")

    def generate_title(self, new_question: str, response: str):
        """
        Generates title with given prompt and response. It generates another completion for title based on first \
        interaction between user and AI.
        :param new_question:
        :param response:
        :return: str
        """
        title_str = f"""
                        ---BEGIN CONVERSATION---
                        User: {new_question}
                        AI: {response}
                        ---END CONVERSATION---
                        Summarize the conversation in 5 words or fewer in user's language:
                    """
        title = self.get_response(INSTRUCTIONS, self.prev_q_a, title_str)
        item = self.nav_drawer.ids[f"item_{self.chat_count}"]
        item.text = title
        item.add_widget(IconRightWidget(icon="delete", on_release=self.delete_chat_log))
        return title

    def save_chat_log(self, title: str):
        """
        Saves the chat log to the firebase database.
        :param title:
        :return: None
        """
        if self.login_check:
            user = auth_firebase.get_account_info(self.user["idToken"])
            email = self.replace_str(user["users"][0]["email"], "to_db")
            chat_id = self.replace_str(title, "to_db")

            for i, (prompt, answer) in enumerate(self.prev_q_a):
                prompt_key = f"prompt_{i + 1}"
                answer_key = f"answer_{i + 1}"
                db.child("chats").child(email).child(chat_id).child(prompt_key).set(
                    prompt
                )
                db.child("chats").child(email).child(chat_id).child(answer_key).set(
                    answer
                )

    def get_chat_log(self):
        """
        Retrieves the chat log from the firebase database.
        :return: None
        """
        if (
                db.child("chats").get().val() is not None
                and db.child("chats")
                .child(self.replace_str(self.user["email"], "to_db"))
                .get()
                .val() is not None
        ):
            chats = db.child("chats").child(
                self.replace_str(self.user["email"], "to_db")
            )
            chat_id = 0
            for chat in chats.get().each():
                chat_layout = ChatLayout(chat_id=chat_id)
                chat_id += 1

                prompt_bubbles = []
                answer_bubbles = []

                title = self.replace_str(chat.key(), "from_db")

                for item in chat.val().items():
                    if item[0].split("_")[0] == "prompt":
                        cb_parent = ChatBubble(
                            pos_hint={"right": 1}, halign="right", btype="m"
                        )
                        cb_relative = cb_parent.children[0]
                        cb_relative.remove_widget(cb_relative.children[0])
                        cb_label = cb_parent.ids.chat_bubble_text
                        cb_label.text = item[1]
                        prompt_bubbles.append(cb_parent)
                        self.cb_label = cb_label

                    if item[0].split("_")[0] == "answer":
                        if len(item[1]) > 200:
                            cb_parent = ChatBubble(
                                pos_hint={"left": 1}, halign="left", btype="r"
                            )
                            cb_parent.full_text = item[1]
                            self.cb_box = cb_parent.children[0].children[0]

                            cb_label = cb_parent.ids.chat_bubble_text
                            cb_label.text = item[1][:200] + "..."

                            self.read_more_button = MDFlatButton(
                                text="Read \nmore",
                                pos_hint={"bottom": 0.0, "right": 1.0},
                                font_size="12sp",
                                on_release=self.read_more_expand,
                            )

                            self.cb_box.add_widget(self.read_more_button)

                            answer_bubbles.append(cb_parent)
                            self.cb_label = cb_label
                        else:
                            cb_parent = ChatBubble(
                                pos_hint={"left": 1}, halign="left", btype="r"
                            )
                            cb_parent.full_text = item[1]
                            cb_label = cb_parent.ids.chat_bubble_text
                            cb_label.text = item[1]
                            answer_bubbles.append(cb_parent)
                            self.cb_label = cb_label

                if self.chat_count == 0:
                    chat_layout = self.chat_layouts[0]
                    chat_children = chat_layout.children[0].children[0]

                    item = self.nav_drawer.ids[f"item_{self.chat_count}"]
                    item.text = title
                    right_widget = IconRightWidget(
                        icon="delete", on_release=self.delete_chat_log
                    )
                    item.add_widget(right_widget)

                    for i in range(len(prompt_bubbles)):
                        prompt_bubble = prompt_bubbles[i]
                        answer_bubble = answer_bubbles[i]

                        prompt_text = (
                            prompt_bubble.children[0].children[0].children[0].text
                        )
                        answer_text = answer_bubble.full_text

                        session_id = f"item_{self.chat_count}"
                        prompt_answer_pair = (prompt_text, answer_text)

                        existing_session = next(
                            (
                                session
                                for session in self.chat_sessions
                                if session[0] == session_id
                            ),
                            None,
                        )

                        if existing_session is not None:
                            existing_session[1].append(prompt_answer_pair)
                        else:
                            self.chat_sessions.append(
                                (session_id, [prompt_answer_pair])
                            )

                        if prompt_bubble.parent is not None:
                            prompt_bubble.parent.remove_widget(prompt_bubble)
                        chat_children.add_widget(prompt_bubble)

                        if answer_bubble.parent is not None:
                            answer_bubble.parent.remove_widget(answer_bubble)
                        chat_children.add_widget(answer_bubble)

                    md_list = self.nav_drawer.ids.chat_list
                    list_item = OneLineAvatarIconListItem(
                        text="New Chat",
                        _txt_left_pad=dp(8),
                        on_release=self.switch_session,
                        fake_id=self.chat_count + 1,
                    )
                    md_list.add_widget(list_item)
                    self.chat_count += 1
                    self.nav_drawer.ids[f"item_{self.chat_count}"] = list_item
                else:
                    chat_children = chat_layout.children[0].children[0]
                    item = self.nav_drawer.ids[f"item_{self.chat_count}"]
                    item.text = title
                    right_widget = IconRightWidget(
                        icon="delete", on_release=self.delete_chat_log
                    )
                    item.add_widget(right_widget)

                    for i in range(len(prompt_bubbles)):
                        prompt_bubble = prompt_bubbles[i]
                        answer_bubble = answer_bubbles[i]

                        prompt_text = (
                            prompt_bubble.children[0].children[0].children[0].text
                        )
                        answer_text = answer_bubble.full_text

                        session_id = f"item_{self.chat_count}"
                        prompt_answer_pair = (prompt_text, answer_text)

                        existing_session = next(
                            (
                                session
                                for session in self.chat_sessions
                                if session[0] == session_id
                            ),
                            None,
                        )

                        if existing_session is not None:
                            existing_session[1].append(prompt_answer_pair)
                        else:
                            self.chat_sessions.append(
                                (session_id, [prompt_answer_pair])
                            )

                        if prompt_bubble.parent is not None:
                            prompt_bubble.parent.remove_widget(prompt_bubble)
                        chat_children.add_widget(prompt_bubble)

                        if answer_bubble.parent is not None:
                            answer_bubble.parent.remove_widget(answer_bubble)
                        chat_children.add_widget(answer_bubble)

                    self.chat_layouts.append(chat_layout)

                    md_list = self.nav_drawer.ids.chat_list
                    list_item = OneLineAvatarIconListItem(
                        text="New Chat",
                        _txt_left_pad=dp(8),
                        on_release=self.switch_session,
                        fake_id=self.chat_count + 1,
                    )
                    md_list.add_widget(list_item)
                    self.chat_count += 1
                    self.nav_drawer.ids[f"item_{self.chat_count}"] = list_item

            chat_layout = ChatLayout(chat_id=chat_id)
            self.chat_layouts.append(chat_layout)

            self.switch_session(self.nav_drawer.ids[f"item_{self.chat_count}"])
        else:
            return

    def delete_chat_log(self, obj):
        """
        Deletes chat_log from the firebase database.
        :param obj:
        :return: None
        """
        md_list = self.nav_drawer.ids.chat_list
        list_item = obj.parent.parent
        md_list.remove_widget(list_item)

        chats = (
            db.child("chats")
            .child(self.replace_str(self.user["email"], "to_db"))
            .child(self.replace_str(obj.parent.parent.text, "to_db"))
        )
        chats.remove()

        chat_layout = self.chat_layouts[list_item.fake_id]
        self.title = list_item.text

        chat_layout.children[0].children[0].clear_widgets()
        self.add_new_chat()
        self.switch_session(self.nav_drawer.ids[f"item_{self.chat_count}"])

    def send_message(self):
        """
        Sends message.
        :return: None
        """
        text_field = self.send_layout.ids.text_field
        message_text = text_field.text.strip()
        if message_text != "":
            cb_parent = ChatBubble(pos_hint={"right": 1}, halign="right", btype="m")
            cb_relative = cb_parent.children[0]
            cb_relative.remove_widget(cb_relative.children[0])
            cb_label = cb_parent.ids.chat_bubble_text
            cb_label.text = message_text
            chat_children = self.chat_layout.children[0].children[0]
            chat_children.add_widget(cb_parent)
            self.cb_label = cb_label
            self.clear_text(text_field)
            self.show_response()
        else:
            self.dialog_open("Blank Prompt", "Input a valid prompt.", "Retry")
            return

    def show_response(self):
        """
        Shows response.
        :return: None
        """
        self.response = self.completion()

        if self.response:
            if len(self.response) > 200:
                cb_parent = ChatBubble(pos_hint={"left": 1}, halign="left", btype="r")
                self.cb_box = cb_parent.children[0].children[0]
                cb_parent.full_text = self.response
                cb_label = cb_parent.ids.chat_bubble_text
                cb_label.text = self.response[:200] + "..."

                self.read_more_button = MDFlatButton(
                    text="Read \nmore",
                    pos_hint={"bottom": 0.0, "right": 1.0},
                    font_size="12sp",
                    on_release=self.read_more_expand,
                )

                self.cb_box.add_widget(self.read_more_button)
                chat_children = self.chat_layout.children[0].children[0]
                chat_children.add_widget(cb_parent)
                self.cb_label = cb_label
            else:
                cb_parent = ChatBubble(pos_hint={"left": 1}, halign="left", btype="r")
                cb_parent.full_text = self.response
                cb_label = cb_parent.ids.chat_bubble_text
                cb_label.text = self.response
                chat_children = self.chat_layout.children[0].children[0]
                chat_children.add_widget(cb_parent)
                self.cb_label = cb_label

            self.save_chat_log(self.title)

    @staticmethod
    def read_more_expand(obj):
        """
        Expands the chat bubble.
        :param obj:
        :return: None
        """
        obj.parent.parent.children[1].children[0].text = obj.parent.parent.parent.full_text
        obj.parent.remove_widget(obj)

    def add_new_chat(self):
        """
        Creates new chat.
        :return: None
        """
        item = self.nav_drawer.ids[f"item_{self.chat_count}"]
        if not item.text == "New Chat":
            md_list = self.nav_drawer.ids.chat_list
            list_item = OneLineAvatarIconListItem(
                text="New Chat",
                _txt_left_pad=dp(8),
                on_release=self.switch_session,
                fake_id=self.chat_count + 1,
            )
            md_list.add_widget(list_item)
            self.chat_count += 1
            self.nav_drawer.ids[f"item_{self.chat_count}"] = list_item

            chat_id = self.chat_layout.chat_id + 1
            chat_layout = ChatLayout(chat_id=chat_id)

            self.chat_layouts.append(chat_layout)

            self.home_screen.remove_widget(self.chat_layout)
            self.home_screen.add_widget(chat_layout, index=2)

            self.chat_layout = chat_layout
            self.prev_q_a = []

        else:
            return

    def switch_session(self, obj):
        """
        Switches between sessions based on clicked item.
        :param obj:
        :return: None
        """
        id_dict = self.nav_drawer.ids
        item_id = list(id_dict.keys())[list(id_dict.values()).index(obj)]
        item = id_dict[f"{item_id}"]
        chat_id = int(item_id.split("_")[1])
        chat_layout = self.chat_layouts[chat_id]

        if chat_layout.parent is not None:
            chat_layout.parent.remove_widget(chat_layout)

        self.home_screen.add_widget(chat_layout, index=2)

        self.chat_layout = chat_layout

        for session_item_id, prev_q_a in self.chat_sessions:
            if session_item_id == item_id:
                self.prev_q_a = prev_q_a
                break
        else:
            self.prev_q_a = []

        self.title = item.text
        self.clear_text(self.send_layout.ids.text_field)

        self.nav_drawer.ids.nav_drawer.set_state("closed")

    @staticmethod
    def replace_str(string: str, type_of: str):
        """
        Performs basic replacing action. Firebase Realtime Database not accepts "." and "?" characters.
        :param string:
        :param type_of:
        :return: str
        """
        if type_of == "to_db":
            replaced_str = (
                string.replace(".", "-dot-").replace("?", "-ask-").replace("'", "")
            )
            return replaced_str
        if type_of == "from_db":
            replaced_str = string.replace("-dot-", ".").replace("-ask-", "?")
            return replaced_str


# TODO: Mesaj gönderdiğinde yazıyor gibi bir animasyon gelmeli, bu animasyon ekranda belirdiğinde eş zamanlı olarak
#  response üretilmeli, daha sonra animasyon kaybolup response gösterilmeli


if __name__ == "__main__":
    app = MainApp()
    app.run()
