"""Every word the bot says lives here.

The client is not technical. Nothing in this file may mention error codes or
technical concepts; tests/test_texts.py enforces it. Names coming from users must go
through esc() because messages are sent as HTML.
"""

from html import escape as esc  # noqa: F401 - used by handlers as texts.esc

# --- General ---
SOMETHING_WRONG = "Sorry, that didn't work this time. Please try again in a moment."
BUTTON_EXPIRED = "This button has expired. Please start again."
BANNED = "Sorry, you can't use this bot."
UNKNOWN_MESSAGE = "Open one of the shared links to get your files. Send /start to learn more."
ONLY_HERE_IN_PRIVATE = "Please use this bot in a private chat."
CANCELLED = "Okay, cancelled."
NOTHING_TO_CANCEL = "There's nothing to cancel right now."

# --- Welcome ---
WELCOME = (
    "<b>Welcome, {name}!</b>\n\n"
    "I keep files safe and deliver them through shareable links.\n"
    "Open a link you were given and your files will arrive here."
)
HELP_USER = (
    "<b>How it works</b>\n\n"
    "1. Open a link you were given.\n"
    "2. If asked, join or subscribe to the listed channels.\n"
    "3. Your files arrive here automatically."
)
HELP_STAFF = (
    "<b>What you can do</b>\n\n"
    "/genlink - store messages and get one link\n"
    "/universal_link - store messages and get one link\n"
    "/batch - store a range of posts from a channel\n"
    "/special_link - a link you can edit later\n"
    "/shortener - shorten any link\n"
    "/broadcast - send a message to all users\n"
    "/ban and /unban - manage users\n"
    "/cancel - stop what you're doing\n\n"
    "Tip: links include the bot's username, so changing the username in BotFather "
    "stops older links from working."
)
HELP_OWNER_EXTRA = "\n/settings - captions, buttons, force subscribe, moderators and more"
ABOUT = "<b>About</b>\n\nA private file store. Files stay safe and are delivered through links."
BTN_HELP = "Help"
BTN_ABOUT = "About"
BTN_BACK = "« Back"
BTN_UPDATE_CHANNEL = "Update Channel"
BTN_CANCEL = "Cancel"
BTN_DONE = "✅ Done"

# --- Moderation ---
BAN_USAGE = "To ban someone, send <code>/ban @username</code> or <code>/ban 123456</code>."
UNBAN_USAGE = "To unban someone, send <code>/unban @username</code> or <code>/unban 123456</code>."
USER_NOT_FOUND = (
    "I don't know that person yet because they haven't used this bot. "
    "Try again with their numeric user number, or once they've opened the bot."
)
CANT_BAN_OWNER = "The bot owner can't be banned."
CANT_BAN_STAFF = "Moderators can't be banned. The owner can remove them in /settings first."
BANNED_OK = "Done. <code>{user_id}</code> can no longer use this bot."
UNBANNED_OK = "Done. <code>{user_id}</code> can use this bot again."
ALREADY_BANNED = "<code>{user_id}</code> is already banned."
NOT_BANNED = "<code>{user_id}</code> isn't banned."

# --- Bot commands shown in Telegram's menu ---
CMD_START = "Check i am alive"
CMD_GENLINK = "To store single or multiple random messages"
CMD_UNIVERSAL = "Stores multiple messages in one link"
CMD_BATCH = "To store multiple messages from a channel"
CMD_SPECIAL = "Store multiple messages and get an editable link (moderators)"
CMD_SHORTENER = "To shorten any shareable links"
CMD_SETTINGS = "Customize your settings as your need"
CMD_BROADCAST = "Broadcast a message to users (moderators only)"
CMD_BAN = "Ban a user (moderators only)"
CMD_UNBAN = "Unban a user (moderators only)"
CMD_CANCEL = "Stop what you're doing"

# --- Storing and links ---
COLLECT_PROMPT = (
    "Send me the messages or files you want to store, then tap <b>Done</b>.\n"
    "You can send as many as you like."
)
COLLECT_REPLIED = (
    "<b>Stored Messages: {count}</b>\n\n"
    "Want to add more messages? Just send them here!\n\n"
    "✨ You can now send multiple messages at once."
)
COLLECT_COUNT = "Added. {count} ready so far. Tap <b>Done</b> when you've finished."
COLLECT_EMPTY = "You haven't sent anything yet. Send a message or file first."
COLLECT_UNSUPPORTED = "This type of message can't be stored. Please send something else."
COLLECT_COMMAND_HINT = "Tap <b>Done</b> to finish, or /cancel to stop."
COLLECT_LIMIT = "That's the most one link can hold. Tap <b>Done</b> to create it."
STORING = "Saving your files…"
LINK_READY = "<b>Here Is Your Link:</b>\n\n\n{link}"
BTN_SHARE_LINK = "Share Link"
STORAGE_BLOCKED = (
    "I can't save to your backup channel. "
    "Please make me an admin there with permission to post, then try again."
)
STORE_NOTHING_SAVED = (
    "I couldn't save those messages. They may have been deleted. Please try again."
)
LINK_GONE = "Sorry, this link is no longer available."
FILES_GONE = "Sorry, the files in this link are no longer available."
SOME_FILES_GONE = "Some files in this link are no longer available. Here's everything else."
DELIVERY_TAIL_BUTTON = "Here you go."

# --- Batch ---
BATCH_FIRST = (
    "Forward me the <b>first</b> post from your channel, or send its link.\n"
    "I need to be an admin in that channel."
)
BATCH_LAST = "Now forward me the <b>last</b> post, or send its link."
BATCH_NOT_A_POST = (
    "That doesn't look like a channel post. Forward one from the channel or send its link."
)
BATCH_DIFFERENT_CHANNEL = (
    "Both posts must come from the same channel. Please send the last post again."
)
BATCH_NOT_ADMIN = "I need to be an admin in that channel. Please add me and try /batch again."
BATCH_PROTECTED = (
    "That channel doesn't allow its content to be copied. "
    'Turn off "Restrict saving content" in its settings and try /batch again.'
)
BATCH_TOO_MANY = "That's {count} posts, and the most I can store at once is {limit}. Please choose a smaller range."
BATCH_PROGRESS = "Saving posts… {done} of {total}"
BATCH_DONE = "<b>Your link is ready</b> ({count} saved)\n\n{link}"
BATCH_EMPTY = "I couldn't find any posts to save in that range."
BATCH_FAILED = "I couldn't finish saving those posts. Please check I'm still an admin there and try /batch again."

# --- Special links ---
SPECIAL_MENU = "<b>Editable links</b>\n\nCreate a new one, or choose one to change. The link itself never changes."
SPECIAL_NEW = "➕ New editable link"
SPECIAL_NAME_PROMPT = "What should this link be called? It's only shown to you and your moderators."
SPECIAL_NAME_INVALID = "Please send a short name, up to 60 characters."
SPECIAL_UNTITLED = "Untitled"
SPECIAL_VIEW = "<b>{title}</b>\n{count} item(s)\n\n{link}"
SPECIAL_ADD = "➕ Add messages"
SPECIAL_ITEMS = "✏️ Reorder or remove"
SPECIAL_DELETE = "🗑 Delete link"
SPECIAL_ITEMS_TITLE = "Use the arrows to reorder, or 🗑 to remove an item."
SPECIAL_ITEM_FALLBACK = "Item {number}"
SPECIAL_NO_ITEMS = "This link has nothing in it yet."
SPECIAL_DELETE_CONFIRM = (
    "Delete <b>{title}</b>? Anyone with this link will no longer be able to open it."
)
SPECIAL_DELETE_YES = "Yes, delete it"
SPECIAL_DELETED = "Deleted."
SPECIAL_STALE = "Someone else just changed this link. Here's the latest version."
SPECIAL_UPDATED = "Updated. The link stays the same."

# --- Shortener ---
SHORTENER_PROMPT = "Send me the link you want to shorten."
SHORTENER_NOT_SET_OWNER = (
    "The link shortener isn't set up yet. Open /settings, then Link Shortener."
)
SHORTENER_NOT_SET_MOD = "The link shortener isn't set up yet. Please ask the owner to set it up."
SHORTENER_BAD_LINK = "That doesn't look like a link. It should start with https://"
SHORTENER_RESULT = "<b>Your short link</b>\n\n{link}"
SHORTENER_FAILED = "I couldn't shorten that link right now. Please try again later."

# --- Settings ---
SETTINGS_TITLE = "<b>🛠 Settings</b>\n\n<i>Customize your settings as your need</i>"
BTN_BACKUP = "Backup 💾"
BTN_SHORTENER = "Link Shortener 📎"
BTN_CAPTION = "Custom Caption 🖌"
BTN_BUTTON = "Custom Button ✳️"
BTN_PROTECT_ON = "Protect Content: ON ☂️"
BTN_PROTECT_OFF = "Protect Content: OFF ☂️"
BTN_FORCE_SUB = "Force Subscribe 📣"
BTN_MODERATORS = "Moderators 👥"
BTN_SET_UPDATE_CHANNEL = "Update Channel 📟"
BTN_CHANGE = "Change"
BTN_REMOVE = "Remove"
BTN_TURN_ON = "Turn on"
BTN_TURN_OFF = "Turn off"
PROTECT_ON = "Protect Content is on. Files can't be forwarded or saved."
PROTECT_OFF = "Protect Content is off."
NOT_SET = "Not set"

CAPTION_VIEW = (
    "<b>Custom Caption</b>\n\nCurrent caption:\n{current}\n\n"
    "This replaces the caption on delivered files."
)
CAPTION_PROMPT = (
    "Send the new caption. You can use:\n"
    "<code>{filename}</code> - the file's name\n"
    "<code>{filesize}</code> - the file's size\n"
    "<code>{caption}</code> - the file's original caption"
)
CAPTION_TOO_LONG = "That's too long. Please keep it under 1000 characters."
CAPTION_SAVED = "Caption saved."
CAPTION_REMOVED = "Caption removed. Files will keep their original captions."

BUTTON_VIEW = "<b>Custom Button</b>\n\nCurrent button: {current}\n\nThis button appears under delivered files."
BUTTON_PROMPT = (
    "Send the button text and link like this:\n<code>Join us - https://t.me/example</code>"
)
BUTTON_INVALID = (
    "I couldn't read that. Please use this format:\n<code>Join us - https://t.me/example</code>"
)
BUTTON_SAVED = "Button saved."
BUTTON_REMOVED = "Button removed."

SHORTENER_VIEW = "<b>Link Shortener</b>\n\nStatus: {status}\nSite: {site}\n\nWhen on, new links are shortened automatically."
SHORTENER_STATUS_ON = "On"
SHORTENER_STATUS_OFF = "Off"
SHORTENER_SITE_PROMPT = "Send your shortener's website, for example <code>example.com</code>"
SHORTENER_SITE_INVALID = (
    "That doesn't look like a website. Try something like <code>example.com</code>"
)
SHORTENER_KEY_PROMPT = (
    "Now send your key. You'll find it in your shortener account, usually under Tools or Developer."
)
SHORTENER_CHECKING = "Checking your shortener…"
SHORTENER_SAVED = "All set. New links will be shortened automatically."
SHORTENER_CHECK_FAILED = "I couldn't get a short link using those details. Please check your website and key, then try again."
SHORTENER_REMOVED = "Link shortener removed."

UPDATE_CHANNEL_VIEW = "<b>Update Channel</b>\n\nCurrent link: {current}\n\nThis appears as a button on the welcome message."
UPDATE_CHANNEL_PROMPT = "Send the link to your update channel."
UPDATE_CHANNEL_SAVED = "Update channel saved."
UPDATE_CHANNEL_REMOVED = "Update channel removed."

BACKUP_VIEW = (
    "<b>Backup</b>\n\nYour files are stored in your backup channel, and a copy of your link list "
    "is saved there every day.\n\nLast backup: {last}"
)
BACKUP_NEVER = "Not yet"
BACKUP_NOW = "Back up now"
BACKUP_DONE = "Backup saved to your channel."
BACKUP_FAILED = "I couldn't save the backup. Please make sure I'm an admin in your backup channel."
BACKUP_CAPTION = "Backup, {date}"
BACKUP_CHANNEL_NOTICE = (
    "I can't post in your backup channel, so new files can't be saved. "
    "Please make me an admin there with permission to post."
)

MODERATORS_VIEW = "<b>Moderators</b>\n\nThey can create links, broadcast and ban users.\n\n{names}"
MODERATORS_NONE = "No moderators yet."
MODERATOR_ADD = "➕ Add moderator"
MODERATOR_PROMPT = "Send the moderator's username, like <code>@name</code>."
MODERATOR_ADDED = "{name} is now a moderator. They get access as soon as they open the bot."
MODERATOR_ALREADY = "They're already a moderator."
MODERATOR_IS_OWNER = "You're the owner, so you already have full access."
MODERATOR_INVALID = "That doesn't look like a username. Please send it like <code>@name</code>."
MODERATOR_REMOVED = "Moderator removed."

# --- Force subscribe settings ---
FS_VIEW = (
    "<b>Force Subscribe</b>\n\n"
    "People must follow everything listed here before getting files. "
    "They only need to do it once per channel.\n\n{items}"
)
FS_NONE = "Nothing added yet, so files are delivered straight away."
FS_ADD_TELEGRAM_CHANNEL = "➕ Telegram channel"
FS_ADD_TELEGRAM_GROUP = "➕ Telegram group"
FS_ADD_YOUTUBE = "➕ YouTube"
FS_ADD_TIKTOK = "➕ TikTok"
FS_ITEM_VIEW = "<b>{name}</b>\n{platform}\n{url}"
FS_PLATFORM_TELEGRAM = "Telegram"
FS_PLATFORM_YOUTUBE = "YouTube"
FS_PLATFORM_TIKTOK = "TikTok"
FS_EDIT_NAME = "✏️ Fix name"
FS_REPLACE = "🔄 Change to another channel"
FS_ASK_AGAIN = "🔁 Ask everyone again"
FS_REMOVE = "🗑 Remove"
FS_ASK_AGAIN_CONFIRM = "Everyone will have to confirm <b>{name}</b> again. Continue?"
FS_ASK_AGAIN_YES = "Yes, ask everyone again"
FS_ASK_AGAIN_DONE = "Done. Everyone will be asked for {name} again."
FS_REMOVED = "Removed. Nobody will be asked for this any more."
FS_ADDED = "Added <b>{name}</b>. Everyone who hasn't done this yet will be asked for it."
FS_READDED = "<b>{name}</b> is back. People who already followed it won't be asked again."
FS_ALREADY = "<b>{name}</b> is already on your list."
FS_REPLACED = "Changed to <b>{name}</b>. Everyone will be asked to follow it."
FS_RENAMED = "Name updated. Nobody will be asked again."
FS_NAME_INVALID = "Please send a name up to 100 characters."
FS_PICK_CHANNEL = (
    "Tap the button below and choose your channel. I'll ask you to make me an admin there."
)
FS_PICK_GROUP = (
    "Tap the button below and choose your group. I'll ask you to make me an admin there."
)
FS_PICK_BUTTON_CHANNEL = "Choose channel"
FS_PICK_BUTTON_GROUP = "Choose group"
FS_PICK_FALLBACK = "Please tap the button below to choose, or send /cancel to stop."
FS_NOT_ADMIN = (
    "I need to be an admin in <b>{name}</b> with permission to add members. "
    "Please make me an admin and try again."
)
FS_CHAT_UNREACHABLE = "I can't reach that chat. Please add me as an admin there and try again."
FS_LINK_PROMPT_YOUTUBE = "Send the link to the YouTube channel, for example:\n<code>https://youtube.com/@yourchannel</code>"
FS_LINK_PROMPT_TIKTOK = (
    "Send the link to the TikTok profile, for example:\n<code>https://tiktok.com/@yourname</code>"
)
FS_LINK_VIDEO_YOUTUBE = "That's a link to a video. Please send the link to the channel, like:\n<code>https://youtube.com/@yourchannel</code>"
FS_LINK_INVALID_YOUTUBE = (
    "I couldn't read that link. Please send it like:\n<code>https://youtube.com/@yourchannel</code>"
)
FS_LINK_INVALID_TIKTOK = (
    "I couldn't read that link. Please send it like:\n<code>https://tiktok.com/@yourname</code>"
)
FS_NAME_PROMPT = (
    "What's the channel's name exactly as it appears on the page? "
    "I look for this name in people's screenshots."
)
FS_CHAT_NOTICE = (
    "I can no longer check <b>{name}</b>, so people aren't being asked to join it. "
    "Please make me an admin there again."
)

# --- Force subscribe for users ---
GATE_TITLE = "<b>Almost there!</b> {done} of {total} done."
GATE_TELEGRAM_LINE = "• Join <b>{name}</b> on Telegram"
GATE_YOUTUBE_LINE = "• Subscribe to <b>{name}</b> on YouTube, then send a screenshot"
GATE_TIKTOK_LINE = "• Follow <b>{name}</b> on TikTok, then send a screenshot"
GATE_SCREENSHOT_HELP = (
    "\n\nThe screenshot should show the channel page with the <b>Subscribed</b> or "
    "<b>Following</b> button. You only need to do this once."
)
GATE_TAIL = "\n\nYour files will arrive as soon as you're done."
GATE_JOIN_BUTTON = "Join {name}"
GATE_YOUTUBE_BUTTON = "YouTube: {name}"
GATE_TIKTOK_BUTTON = "TikTok: {name}"
GATE_CHECK_BUTTON = "✅ I've joined"
GATE_NOT_YET = "You haven't joined everything yet."
SCREENSHOT_CHECKING = "Checking your screenshot…"
SCREENSHOT_OK = "Thanks, that's confirmed."
SCREENSHOT_NOT_SUBSCRIBED_YOUTUBE = (
    "It looks like you haven't subscribed to <b>{name}</b> yet. "
    "Subscribe, then send a new screenshot showing <b>Subscribed</b>."
)
SCREENSHOT_NOT_FOLLOWING_TIKTOK = (
    "It looks like you aren't following <b>{name}</b> yet. "
    "Follow, then send a new screenshot of the profile page."
)
SCREENSHOT_UNCLEAR = (
    "I couldn't read that one. Please send a clear screenshot of the <b>{name}</b> page "
    "showing the button you tapped."
)
SCREENSHOT_NOT_NEEDED = (
    "You're all set, there's nothing to confirm right now. Open a link to get your files."
)
SCREENSHOT_JOIN_FIRST = (
    "No screenshot needed for this one. Just join the channels above and tap <b>I've joined</b>."
)
SCREENSHOT_WRONG_TYPE = "Please send a screenshot as a picture."
SCREENSHOT_TOO_BIG = "That picture is too large. Please send a normal screenshot."

# --- Broadcast ---
BROADCAST_PROMPT = "Send me the message you want to broadcast to everyone."
BROADCAST_PREVIEW = "This is how it will look. Send it to {count} user(s)?"
BROADCAST_SEND = "📣 Send to everyone"
BROADCAST_BUSY = "Another broadcast is still running. Please wait for it to finish."
BROADCAST_PROGRESS = "Broadcasting… {sent} sent so far."
BROADCAST_STOP = "⏹ Stop"
BROADCAST_DONE = "<b>Broadcast finished</b>\n\nDelivered: {sent}\nCouldn't receive it: {failed}"
BROADCAST_STOPPED = "<b>Broadcast stopped</b>\n\nDelivered: {sent}\nCouldn't receive it: {failed}"
BROADCAST_SOURCE_GONE = (
    "I stopped the broadcast because the original message was deleted. Delivered: {sent}"
)
BROADCAST_NOT_COPYABLE = "This type of message can't be broadcast. Please send something else."
BROADCAST_NO_USERS = "There's nobody to send this to yet."

# --- Logs group ---
LOG_ACTOR = "{name} (<code>{user_id}</code>)"
LOG_NEW_USER = "👤 New user: {actor}"
LOG_LINK_CREATED = "🔗 {actor} created a link ({count} item(s))\n{link}"
LOG_LINK_EDITED = "✏️ {actor} changed an editable link\n{link}"
LOG_LINK_DELETED = "🗑 {actor} deleted the editable link <b>{title}</b>"
LOG_BROADCAST_STARTED = "📣 {actor} started a broadcast"
LOG_BROADCAST_DONE = "📣 Broadcast finished. Delivered: {sent}. Couldn't receive it: {failed}."
LOG_BROADCAST_STOPPED = "📣 Broadcast stopped. Delivered: {sent}. Couldn't receive it: {failed}."
LOG_BANNED = "🚫 {actor} banned <code>{user_id}</code>"
LOG_UNBANNED = "✅ {actor} unbanned <code>{user_id}</code>"
LOG_FS_ADDED = "📢 {actor} added to force subscribe: <b>{name}</b> ({platform})\n{url}"
LOG_FS_READDED = "📢 {actor} brought back to force subscribe: <b>{name}</b> ({platform})"
LOG_FS_REMOVED = "📢 {actor} removed from force subscribe: <b>{name}</b> ({platform})"
LOG_FS_REPLACED = "📢 {actor} changed <b>{old}</b> to <b>{name}</b> ({platform})\n{url}"
LOG_FS_RENAMED = "📢 {actor} renamed a force subscribe channel to <b>{name}</b>"
LOG_FS_ASKED_AGAIN = "📢 {actor} asked everyone to confirm <b>{name}</b> again"
LOG_SETTING_CAPTION = "⚙️ {actor} changed the custom caption"
LOG_SETTING_CAPTION_OFF = "⚙️ {actor} removed the custom caption"
LOG_SETTING_BUTTON = "⚙️ {actor} changed the custom button"
LOG_SETTING_BUTTON_OFF = "⚙️ {actor} removed the custom button"
LOG_SETTING_PROTECT_ON = "⚙️ {actor} turned Protect Content on"
LOG_SETTING_PROTECT_OFF = "⚙️ {actor} turned Protect Content off"
LOG_SETTING_SHORTENER = "⚙️ {actor} set up the link shortener: {site}"
LOG_SETTING_SHORTENER_ON = "⚙️ {actor} turned the link shortener on"
LOG_SETTING_SHORTENER_OFF = "⚙️ {actor} turned the link shortener off"
LOG_SETTING_SHORTENER_REMOVED = "⚙️ {actor} removed the link shortener"
LOG_SETTING_UPDATE_CHANNEL = "⚙️ {actor} changed the update channel"
LOG_SETTING_UPDATE_CHANNEL_OFF = "⚙️ {actor} removed the update channel"
LOG_MODERATOR_ADDED = "👥 {actor} added moderator {name}"
LOG_MODERATOR_REMOVED = "👥 {actor} removed a moderator"
LOG_CHAT_NOTICE = (
    "I can't post in your logs group, so you won't see activity there. Please add me to the group."
)

REVIEW_CAPTION = (
    "<b>Please review</b>\n\n"
    "{actor} couldn't pass the <b>{name}</b> ({platform}) check after {attempts} tries, "
    "so I let them through. This is their last screenshot.\n\n"
    "Approve to leave them be. Not Approve bans them from this bot."
)
REVIEW_NO_PICTURE = "\n\nThe screenshot is no longer available."
REVIEW_APPROVE = "✅ Approve"
REVIEW_REJECT = "🚫 Not Approve (ban)"
REVIEW_APPROVED_BY = "✅ Approved by {actor}"
REVIEW_REJECTED_BY = "🚫 Not approved and banned by {actor}"
REVIEW_STAFF_ONLY = "Only the owner and moderators can decide this."
REVIEW_ALREADY_DECIDED = "Someone has already decided this one."
REVIEW_IS_STAFF = "This person is a moderator now. The owner can remove them in /settings first."
