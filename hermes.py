#!/bin/env python3

from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, Filters
from config import TOKEN, LOG_FILE
import requests, re, logging, time, sys

BASE_URL = 'https://www.motaword.com'
headers = {
	'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; rv:71.0) Gecko/20100101 Firefox/71.0'
}
EMAIL_STATE, PASSWORD_STATE = range(2)

# shared variable
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
	logger.info('Logging in to Motaword')
	session = getSession()
	
	r = session.get(BASE_URL + '/login')
	m = re.findall('.*_token" value="(.*)">.*', r.text)
	token = m[0]
	logger.debug(f'The login csrf token is {token}')
	
	r = session.post(BASE_URL + '/login', data={'_token': token, 'email': username, 'password': password})
	logger.debug('Logged in')

def daemonMotaword(context):
	chatId = context.job.context['chatId']
	session = getSession()
	
	logger.debug('Getting projects...')
	r = session.get(BASE_URL + '/vendor/projects', allow_redirects=False)
	if r.status_code == 302:
		motawordLogin(accounts[chatId]['email'], accounts[chatId]['password'])
		return
	
	matches = re.findall('project_[0-9]+', r.text)
	logger.debug(f'Got {len(matches)} projects: {str(matches)}')
	if len(matches) == 0:
		logger.error('Error while fetching projects')
		logger.error(f'{r.status_code}')
		logger.error(f'{r.text}')
		sys.exit(1)
	
	newProjects = []
	oldProjects.setdefault(chatId, matches)
	for projectId in matches:
		if projectId in oldProjects[chatId]:
			continue
		
		divStart = r.text.find(projectId)
		aStart = r.text[divStart:].find('<a class')
		aEnd = r.text[divStart+aStart:].find('</a>')
		aBody = r.text[divStart+aStart:divStart+aStart+aEnd]
		
		if 'disabled' in aBody:
			logger.info(f'{projectId} is not ready yet. It seems to be disabled')
			continue
		
		newProjects.append(projectId)
		oldProjects[chatId].append(projectId)
	if newProjects:
		context.bot.send_message(chat_id=chatId, text=f'Hurry up! There are {len(newProjects)} new projects to translate')

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
	
	updater = Updater(token=TOKEN, use_context=True)
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
