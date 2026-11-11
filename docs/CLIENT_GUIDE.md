# Your File Store Bot: Quick Guide

## Sharing files

**One link for some files**
1. Send `/genlink` to the bot.
2. Send your files or messages. You can send as many as you like.
3. Tap **Done**, and copy your link.

`/universal_link` works the same way.

**Many posts from your channel**
1. Make the bot an admin in that channel.
2. Send `/batch`.
3. Forward the first post, then the last post.
4. The bot saves everything in between and sends you one link.

**A link you can change later**
1. Send `/special_link` and tap **New editable link**.
2. Give it a name, send your files, and tap **Done**.
3. To change it later, send `/special_link` and choose it. You can add, reorder or remove files, and the link stays the same.

Changed your mind part way through? Send `/cancel`.

## Making people subscribe first

Open `/settings`, then **Force Subscribe**. You can add as many as you like, and remove any of them at any time.

- **Telegram channel or group:** tap the button and choose it. Telegram will offer to make the bot an admin. Please accept, because the bot needs this.
- **YouTube or TikTok:** paste the link to the channel, then type its name exactly as it appears on the page. The bot looks for this name in screenshots.

**What your followers see:** a list of what to join, with buttons. For YouTube and TikTok they send one screenshot. Once they've finished, their files arrive automatically.

**They only do this once per channel.** They are only asked again if you:

- add a new channel (they're asked for the new one only)
- change a channel to a different one (they're asked for that one only)
- tap **Ask everyone again** on a channel

Fixing a channel's name, or removing a channel and adding it back later, won't ask anyone again.

**Good to know**
- If someone leaves a Telegram channel, the bot notices and asks them to rejoin.
- For YouTube and TikTok, the bot can't tell if someone unsubscribes later.
- The screenshot must clearly show the **Subscribed** or **Following** button. A cropped picture that doesn't show the button will be asked for again.
- A screenshot can't be fully proven real, so a fake could occasionally get through. After 3 tries that don't pass, the bot lets the person through so that real followers never get stuck, and asks you to review them in your logs group.

## Your logs group

The bot posts what's happening to your logs group: new users, links created, broadcasts, bans, and any change to settings, moderators or force subscribe.

**Reviewing people the bot let through.** If someone's screenshot doesn't pass after 3 tries, the bot still gives them their files, then shows you their last screenshot here with two buttons:

- **Approve:** nothing changes for them.
- **Not Approve:** they're banned from the bot.

Only you and your moderators can press these. Whoever presses first decides. Files they've already received can't be taken back. If you ban someone by mistake, send `/unban` with their user number, and they'll need to send a new screenshot.

## Other settings

Open `/settings` for these:

| Button | What it does |
|---|---|
| **Backup** | Your files are kept in your backup channel, and a copy of your link list is saved there every day. Tap **Back up now** any time. |
| **Link Shortener** | Enter your shortener's website and key, and new links are shortened automatically. |
| **Custom Caption** | Replaces the caption on files. You can use `{filename}`, `{filesize}` and `{caption}`. |
| **Custom Button** | Adds a button under files. Send it like: `Join us - https://t.me/example` |
| **Protect Content** | Stops people forwarding or saving your files. |
| **Moderators** | Add helpers by their @username. |
| **Update Channel** | Adds your channel as a button on the welcome message. |

## Managing people

| Command | What it does |
|---|---|
| `/broadcast` | Send a message to everyone. You see a preview first, and can stop it part way. |
| `/ban @name` | Stops someone using the bot. You can use their user number instead. |
| `/unban @name` | Lets them back in. |
| `/shortener` | Shortens any link. |

**Moderators** can create links, broadcast and ban users. Only you can open `/settings`, and moderators can't ban you or each other.

## Things to avoid

- **Don't remove the bot from your backup channel, or take away its admin rights.** New files couldn't be saved, and existing links would stop working. If this happens, the bot will message you.
- **Don't delete posts from your backup channel.** Links that use those files will stop delivering them.
- **Don't remove the bot from your logs group.** You'd stop seeing activity and reviews, though the bot keeps working. If this happens, the bot will message you.
- **Don't change the bot's username.** Links you've already shared would stop working.
