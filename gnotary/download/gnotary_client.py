"""A proof of concept implementation of a GNotary digital notary client

Requires: Python 2.1 or higher, wxPython 2.3.1 or higher
You can downlod wxPython from http://www.wxpython.org

For details regarding the GNotary concept please visit http://gnumed.net

I wrote this module during a flight from Australia to London. Due to limited
battery life of my notebook I did not have time to finish it yet, nor to
comment and document it properly. It is largely untested, and for
all I know it is probably still full of bugs

@author: Dr. Horst Herb
@copyright: copyleft (GPL) by Dr.Horst Herb
For details regarding the GPL licensing scheme please check http://www.gnu.org
@version: 0.2

CHANGELOG:
24.09.2001 (hherb):	minor bug fix (FileSelection bug)

TODO:
	- COMMENTING & DOCUMENTATION!!!
	- load and save configuration
	- download mail certificates and verify them
	- verify zip files
	- write HELP function
	- create a setup for distutils in order to package it / create a binary with py2exe
"""

#import all of the wxPython GUI package
from wxPython.wx import *
import os.path, md5, time, smtplib, zipfile

# text translation function for localization purposes
import gettext
_ = gettext.gettext


_nofiles_warning = _( \
"""
No files selected to perform action.
You have to select files first.

Do so by dragging and dropping any
number of files using your favourite
file manager (like Konqueror or Explorer)"
""")


class AllFilesIn:
        """Iterates recursively through a given path in a ressource friendly way

	modified after an idea by Frederik Lundh, taken from his
	"Python Standard Library Annotated Reference"
	Example usage:

	for files in AllFilesIn('.'):
		print files

	Do NOT try to alter the index; this class works only as long as the
	iteration happens in the right order
	"""

	def __init__(self, directory, show_directories=1):
		"""
		directory: the path where the iteration shall start
		show_directories: if 0, only file names will be returned (no directory names)
		"""
		if os.path.isdir(directory):
	        	self.stack = [directory]
			self.files = []
		elif os.path.isfile(directory):
	        	self.stack = []
			self.files = [directory]
		else:
			self.stack = []
			self.files = []

		self.index = 0
		self.show_dirs = show_directories
		self.directory = './'

        def __getitem__(self, index):
	        while 1:
		        try:
			        file = self.files[self.index]
				self.index += 1
			except IndexError:
				#pop the next directory
				self.directory = self.stack.pop()
				self.files = os.listdir(self.directory)
				self.index=0
			else:
				#got a filename
				fullname = os.path.join(self.directory, file)
				if os.path.isdir(fullname) and not os.path.islink(fullname):
					self.stack.append(fullname)
					if self.show_dirs:
						return fullname
				else:
					return fullname



def CalculateFileDetails(file, blocksize = 65536, threshold = 1024 ):

	fsize = os.path.getsize(file)
	last_modified = time.strftime(_("%d/%m/%Y %H:%M:%S"), time.gmtime(os.path.getmtime(file)))
	if fsize==0:
		#NO NEED TO CALCULATE HASH FOR AN EMPTY FILE!
		return '', fsize, last_modified

	try:
		inputfile = open(file, 'r')
	except:
		wxLogMessage(_("ERROR (file open): Can't open file %s for hashing") % file)
		return None, 0, None
	hashresult = ''
	# we don't need a progress dialog for small files
	if fsize/1024 < threshold:
		try:
			data =inputfile.read()
		except:
			wxLogMessage(_("ERROR (file read): Can't calculate hash for file %s") % file)
		else:
			if data:
				hashresult = md5.new(data).hexdigest()
		inputfile.close()
		return hashresult, fsize, last_modified

	#this is a big one, show progress dialog
	hash = md5.new()
	bytes_processed = 0
	dlg = wxProgressDialog(_("Patience please"), \
	        _("Calculating hash of file %s (%d kB)") % (file, fsize/1024), \
		fsize, \
		None, \
		wxPD_CAN_ABORT | wxPD_APP_MODAL | wxPD_AUTO_HIDE |wxPD_ELAPSED_TIME)
	keepGoing = true
	while keepGoing:
               	data = inputfile.read(blocksize)
		if not data:
			keepGoing=false
			dlg.Update(bytes_processed, "Finalizing hash calculation")
			hashresult = hash.hexdigest()
		else:
			hash.update(data)
			bytes_processed += len(data)
			keepGoing = dlg.Update(bytes_processed)
	inputfile.close()
	dlg.Destroy()
	return hashresult, fsize, last_modified



class FileDropTarget(wxFileDropTarget):
	"""Customized drag & drop for FileListCtrl class below
	"""

    	def __init__(self, window, log):
        	wxFileDropTarget.__init__(self)
        	self.window = window
        	self.log = log

    	def OnDropFiles(self, x, y, filenames):
		""" Append all dropped files to the FileListCtrl list widget
		"""

		for file in filenames:
			#Iterate recursively through dropped directories and list all files
			for filename in AllFilesIn(file, 0):
				self.window.AddFile(filename)
		#make sure the full length path is visible in the list widget
		self.window.AdjustColumnWidth()



class FileListCtrl(wxListCtrl):
	"""Customized file list control widget with file drag & drop properties

	it displays files, file size & modification date, and it calculates
	a MD5 or SHA checksum for all files.
	"""

	def __init__(self, parent, id, log):
		wxListCtrl.__init__(self, parent, id, style=wxLC_REPORT|wxSUNKEN_BORDER)

		self.log = log
		self.labels = (_("File name"), _("Size"), _("Modified"), _("MD5"))
		count = 0
		for label in self.labels:
			self.InsertColumn(count, self.labels[count])
			count += 1
		dt = FileDropTarget(self, log)
	        self.SetDropTarget(dt)


	def AddFile(self, file):
		if not os.path.isfile(file):
			wxLogMessage(_("ERROR (bizarre): a non-file object reached AddFile(): %s") %file)
			return
		offset = self.GetItemCount()
		md5, fsize, last_modified = CalculateFileDetails(file)
		self.InsertStringItem(offset, file)
		self.SetStringItem(offset, 1, str(fsize))
		self.SetStringItem(offset, 2, last_modified)
		self.SetStringItem(offset, 3, md5)


	def AdjustColumnWidth(self):
		for count in range(len(self.labels)):
			self.SetColumnWidth(count, wxLIST_AUTOSIZE)



class ActionWin(wxPanel):
        def __init__(self, parent, id, log):

		wxPanel.__init__(self, parent, id)
                self.log = log
		self.parent = parent
		self.email = ''
		self.mailserver = 'localhost'
		self.notaries = 'gnotary@gnumed.net'
		self.subject = 'gnotarize'
		#algorithm to use for hashing
		self.hash = md5.md5
		#name of the zipped backup file
		self.zipfile = ''
		#if verify, check hash again after backup to ensure backup integrity
		self.verify = true

		self.topsizer = wxBoxSizer(wxVERTICAL)
		self.buttonsizer = wxBoxSizer(wxHORIZONTAL)

		self.filelist = FileListCtrl(self, id, self.log)
		self.topsizer.Add(self.filelist, 5,  wxGROW | wxALL, 0 )

		id = wxNewId()
		self.sendmailbutton = wxButton(self, id, _("&Notarize") )
		EVT_BUTTON(self, id, self.OnNotarize)
		self.buttonsizer.Add(self.sendmailbutton, 0, wxALL, 1)

		id = wxNewId()
		self.verifybutton = wxButton(self,id, _("&Verify certificate") )
		EVT_BUTTON(self, id, self.OnVerify)
		self.buttonsizer.Add(self.verifybutton, 0, wxALL, 1)

		id = wxNewId()
		self.zipfilesbutton = wxButton(self, id, _("&Backup files") )
		EVT_BUTTON(self, id, self.OnZipFiles)
		self.buttonsizer.Add(self.zipfilesbutton, 0, wxALL, 1)

		id = wxNewId()
		self.loadzipbutton = wxButton(self, id, _("&Verify Zip") )
		EVT_BUTTON(self, id, self.OnLoadZip)
		self.buttonsizer.Add(self.loadzipbutton, 0, wxALL, 1)

		id = wxNewId()
		self.setupbutton = wxButton(self, id, _("&Setup") )
		EVT_BUTTON(self, id, self.OnSetup)
		self.buttonsizer.Add(self.setupbutton, 0, wxALL, 1)

		self.topsizer.AddSizer(self.buttonsizer, 0, wxALL, 0)
		self.SetSizer(self.topsizer)
		self.SetAutoLayout(true)
		self.topsizer.Fit(self)



	def OnNotarize(self, event):
		if self.filelist.GetItemCount() < 1:
			wxMessageBox(_nofiles_warning)
			wxLogMessage(_("No files selected - nothing to notarize"))
			return
		msg,timestamp = self.CreateMessage()
		if msg == None:
			wxLogMessage("Unable to create message!")
			return
		try:
			msgfile = open(timestamp + ".req", "w")
			msgfile.write(msg)
		except:
			wxLogMessage(_("Could not create or write to message file!"))
			return
		msgfile.close()
		server = smtplib.SMTP(self.mailserver)
        #server.set_debuglevel(1)
		server.sendmail(self.email, self.notaries, msg)
		server.quit()
		wxLogMessage("Notary request sent to %s with time stamp %s" % (self.notaries, timestamp))


	def OnVerify(self, event):
		wxLogMessage(_("Sorry, not implemented yet"))


	def OnLoadZip(self,event):
		wxLogMessage(_("Sorry, not implemented yet"))


	def OnZipFiles(self, event):
		if self.filelist.GetItemCount() < 1:
			wxMessageBox(_nofiles_warning)
			wxLogMessage(_("Zipping aborted - no files selected"))
			return
		#get the filename of the zip archive
		self.zipfile = self.PromptForZipfileName()
		if self.zipfile is None:
			wxLogMessage(_("You must specify a file name first"))
			return

		try:
			zip = zipfile.ZipFile(self.zipfile, 'w')
		except IOError:
			wxLogMessage(_("Can't open nor create zip file %s") % self.zipfile)
			return

		dlg = wxProgressDialog(_("Patience please - compressing files"), \
		        _("Compressing files..."), \
			self.filelist.GetItemCount(), \
			self, \
			wxPD_CAN_ABORT | wxPD_APP_MODAL | wxPD_AUTO_HIDE |wxPD_ELAPSED_TIME)
		self.filelist.GetItemCount()
		keepGoing = true
		files_processed = 0
		errors=0
		errormessages = []
		while keepGoing:
			for index in range(self.filelist.GetItemCount()):
				file = self.filelist.GetItemText(index)
				lmodified = self.filelist.GetItem(index, 2).GetText()
				lsize = self.filelist.GetItem(index, 1).GetText()
				lhash = self.filelist.GetItem(index, 3).GetText()

				try:
					infile = open(file, 'r')
				except:
					wxLogMessage(_("Can't open file %s for backup!") % file)
					return
				keepGoing = dlg.Update(files_processed, file)
				zip.write(file, compress_type = zipfile.ZIP_DEFLATED)
				files_processed +=1
				wxLogMessage(_("%s added") % file)
				if self.verify:
					hash, size, modified = CalculateFileDetails(file)
					if hash != lhash:
						#big trouble!!! the file we backed up is not the same
						#as listed in the list widget!!!
						errors+=1
						errmsg = _("ERROR: big trouble. Hash of file in backup (%s) does not match listed hash") % file
						wxLogMessage(errmsg)
						errormessages.append(errmsg)
						#mark the "corrupt" file
						item =self.filelist.GetItem(index)
						item.SetTextColour(wxRED)
						#and show the mark
						self.filelist.SetItem(item)
				keepGoing = dlg.Update(files_processed)
				if not keepGoing:
					wxLogMessage(_("Backup interrupted by user"))
					return
			keepGoing = false
		dlg.Destroy()

		#add a special gnotary archive file representing the information displayed in the list widget
		list = self.ListFileSelection()
		info = zipfile.ZipInfo('gnotary.archive')
		info.date_time = time.localtime(time.time())[:6]
		info.compress_type = zipfile.ZIP_DEFLATED
		zip.writestr(info, list)

		zip.close()
		wxLogMessage(_("%d files added to archive %s") % (files_processed, self.zipfile))
		if errors>0:
			wxLogMessage(_("\n%d errors reported:") % errors)
			for msg in errormessages:
				wxLogMessage(msg)




	def OnSetup(self, event):
		ignore = self.RunSetupDialog()


	def RunSetupDialog(self):
		dlg = SetupDialog(self.parent, -1)
		dlg.CenterOnParent()
		retval = dlg.ShowModal()
		if retval == wxID_OK:
			self.email, self.mailserver, self.notaries, self.subject = dlg.GetSettings()
			dlg.Destroy()
		return retval


	def GetColumnText(self, index, col):
		item = self.filelist.GetItem(index, col)
		return item.GetText()


	def PromptForZipfileName(self):
		filename = None
		dlg = wxFileDialog(self, "Choose a file", ".", "", "*.*", wxSAVE|wxOVERWRITE_PROMPT)
		if dlg.ShowModal() == wxID_OK:
			filename = dlg.GetPath()
		dlg.Destroy()
		return filename


	def ListFileSelection(self):
		msg = ''
		for index in range(self.filelist.GetItemCount()):
		        txt = self.filelist.GetItemText(index)
			for column in range (1, len(self.filelist.labels)):
				txt = "%s\t%s" % (txt, self.GetColumnText(index, column))
			msg = "%s\n%s" % (msg,txt)
		return msg


	def CreateMessage(self):
		timestamp = str(time.time())
		if self.email=='':
			#no point in creatig an email without receiver address
			if self.RunSetupDialog() != wxID_OK:
				wxLogMessage(_("Can't notarize without valid email address!"))
				return None
		msg = ('From: %s\nTo: %s\nSubject: %s\n\n%s' % (self.email, self.notaries, self.subject, self.ListFileSelection()))
		return msg, timestamp



class LogWin(wxPanel):
	def __init__(self, parent, id):
		wxPanel.__init__(self, parent, id)
		sizer = wxBoxSizer(wxVERTICAL)
		self.log = wxTextCtrl(self, -1, '', wxDefaultPosition, wxSize(500,150), wxTE_MULTILINE)
		sizer.Add(self.log, 1, wxGROW|wxALL, 1)
		self.SetSizer(sizer)
		self.SetAutoLayout(true)
		sizer.Fit(self)

	def GetLog(self):
		return self.log




class BackupMainFrame(wxFrame):

	def __init__(self, parent, id, title):
		# First, call the base class' __init__ method to create the frame
		wxFrame.__init__(self, parent, id, title, wxPoint(100, 100), wxSize(600, 400))

		self.splitter = wxSplitterWindow(self, -1, style=wxNO_3D|wxSP_3D)
		self.splitter.SetMinimumPaneSize(20)

		self.LogWin = LogWin(self.splitter, -1)
		wxLog_SetActiveTarget(wxLogTextCtrl(self.LogWin.GetLog()))
		self.ActionWin = ActionWin(self.splitter, -1, self.LogWin.GetLog())

		self.splitter.SplitHorizontally(self.ActionWin, self.LogWin)
		self.splitter.SetMinimumPaneSize(20)

		self.splitter.SetSashPosition(350)


	def OnCloseWindow(self, event):
		# tell the window to kill itself
		self.Destroy()





class SetupDialog(wxDialog):

	def __init__(self, parent, id):

		wxDialog.__init__(self, parent, id, _("GNotary Client Setup") )
		
		sizer = wxBoxSizer(wxVERTICAL)
		
		sizer.AddWindow(wxStaticText(self, -1, _("your email address (certificates will be sent to this address):")))
		self.email = wxTextCtrl(self, -1, '')
		sizer.AddWindow(self.email, 1, wxGROW|wxALL)

		sizer.AddWindow(wxStaticText(self, -1, _("SMTP mail server:")), 0)
		self.mailserver = wxTextCtrl(self, -1, "localhost")
		sizer.AddWindow(self.mailserver, 1, wxGROW|wxALL)

		sizer.AddWindow(wxStaticText(self, -1, _("Notary servers (comma separated list):")))
		self.notaries = wxTextCtrl(self, -1, "gnotary@gnumed.net")
		sizer.AddWindow(self.notaries, 1, wxGROW|wxALL)

		sizer.AddWindow(wxStaticText(self, -1, _("Notary request email 'Subject:'")))
		self.subject = wxTextCtrl(self, -1, "gnotarize")
		sizer.AddWindow(self.subject, 1, wxGROW|wxALL)

		butsizer = wxBoxSizer(wxHORIZONTAL)
		okbut = wxButton(self, wxID_OK, _("&OK"))
		butsizer.AddWindow(okbut, 1, wxGROW|wxALL)
		cancelbut = wxButton(self, wxID_CANCEL, _("&Cancel"))
		butsizer.AddWindow(cancelbut, 1, wxGROW|wxALL)

		sizer.AddSizer(butsizer, 0, wxGROW|wxALL, 5)

		self.SetSizer(sizer)
		self.SetAutoLayout(true)
		sizer.Fit(self)
		#item0.SetSizeHints( self )


	def GetSettings(self):
		return self.email.GetValue(), self.mailserver.GetValue(), self.notaries.GetValue(), self.subject.GetValue()


	def SetSettings(self, email, mailserver, notaries, subject):
		self.email.SetValue(email)
		self.mailserver.SetValue(mailserver)
		self.notaries.SetValue(notaries)
		self.subject.SetValue(subject)



class BackupApp(wxApp):

	def OnInit(self):
		frame = BackupMainFrame(NULL, -1, _("Digital Notary Client by H. Herb"))
		frame.Show(true)
		# Tell wxWindows that this is our main window
		self.SetTopWindow(frame)
		return true




if __name__ == "__main__":
	app = BackupApp(0)     # Create an instance of the application class
	app.MainLoop()     # Tell it to start processing events
