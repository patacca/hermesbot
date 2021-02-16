#!/bin/env python3

from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, Filters
from config import APP_TOKEN, BOT_TOKEN, LOG_FILE
import requests, re, logging, time, sys

BASE_URL = 'https://api.motaword.com'
headers = {
	'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; rv:71.0) Gecko/20100101 Firefox/71.0'
}
EMAIL_STATE, PASSWORD_STATE = range(2)

# shared variable
_TOKEN = None # This is the OAuth2 token for logging in
accounts = {}
oldProjects = {}
_session = None

def getSession():
	global _session
	
	if not _session:
		_session = requests.sessions.Session()
		_session.headers.update(headers)
		return _session
	return _session

def motawordLogin(username, password):
	global _TOKEN
	
	logger.info('Logging in to Motaword')
	session = getSession()
	
	r = session.post(BASE_URL + '/token', headers={'Authorization': f'Basic {APP_TOKEN}'}, data={'grant_type': 'password', 'username': username, 'password': password, 'scope': 'default privileged'})
	if r.ok:
		_TOKEN = r.json()['access_token']
		session.headers.update({'Authorization': f'Bearer {_TOKEN}'})
		logger.debug('Logged in')
	else:
		logger.error(f'Cannot log in: HTTP {r.status_code}')

def daemonMotaword(context):
	chatId = context.job.context['chatId']
	session = getSession()
	
	logger.debug('Getting projects...')
	r = session.get(BASE_URL + '/projects')
	if r.status_code == 401: # Unauthorized
		motawordLogin(accounts[chatId]['email'], accounts[chatId]['password'])
		return
	
	projects = r.json()['projects']
	logger.debug(f'Got {len(projects)} projects: {str(projects)}')
	
	newProjects = []
	oldProjects.setdefault(chatId, [])
	for project in projects:
		if project['id'] in oldProjects[chatId]:
			continue
		
		# Check for status == disabled
		# ~ if 'disabled' in aBody:
			# ~ logger.info(f'{projectId} is not ready yet. It seems to be disabled')
			# ~ continue
		
		newProjects.append(project['id'])
		oldProjects[chatId].append(project['id'])
	if len(newProjects) > 1:
		context.bot.send_message(chat_id=chatId, text=f'Hurry up! There are {len(newProjects)} new projects to translate')
	if len(newProjects) == 1:
		context.bot.send_message(chat_id=chatId, text=f'Hurry up! There is one new project to translate')

def start(update, context):
	if update.effective_chat.id in accounts:
		update.message.reply_text("You are already receiving the notifications")
		return ConversationHandler.END
	
	accounts[update.effective_chat.id] = {}
	logger.debug(f'Chat {update.effective_chat.id}: started')
	update.message.reply_text(
		"Welcome to Hermes, the notification bot for Motaword\n"
		"Write your mail address"
	)
	
	return EMAIL_STATE

def email(update, context):
	emailValue = update.message.text
	logger.debug(f'Chat {update.effective_chat.id}: got mail address {emailValue}')
	accounts[update.effective_chat.id]['email'] = emailValue
	update.message.reply_text("Now write your password")
	
	return PASSWORD_STATE

def password(update, context):
	passwordValue = update.message.text
	logger.debug(f'Chat {update.effective_chat.id}: got password {passwordValue}')
	accounts[update.effective_chat.id]['password'] = passwordValue
	update.message.reply_text("Perfect! You will receive here the notifications")
	
	context.job_queue.run_repeating(daemonMotaword, 30, context={'chatId': update.effective_chat.id})
	
	return ConversationHandler.END

def cancel(update, context):
	accounts.remove(update.effective_chat.id)
	logger.debug(f'Chat {update.effective_chat.id}: cancel conversation')
	update.message.reply_text('Bye!', reply_markup=ReplyKeyboardRemove())
	return ConversationHandler.END

if __name__ == '__main__':
	logger = logging.getLogger(__name__)
	logger.setLevel(logging.DEBUG)
	handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1000*1000*1, backupCount=5)
	formatter = logging.Formatter('%(asctime)s - [%(levelname)s]  %(message)s')
	handler.setFormatter(formatter)
	logger.addHandler(handler)
	
	logger.info('Hermes bot is starting')
	
	updater = Updater(token=BOT_TOKEN, use_context=True)
	dispatcher = updater.dispatcher
	
	conversationHandler = ConversationHandler(
		entry_points=[CommandHandler('start', start)],
		states={
			EMAIL_STATE: [MessageHandler(Filters.text & ~Filters.command, email)],
			PASSWORD_STATE: [MessageHandler(Filters.text & ~Filters.command, password)],
		},
		fallbacks=[CommandHandler('cancel', cancel)],
	)
	dispatcher.add_handler(conversationHandler)
	
	updater.start_polling()
	updater.idle()
