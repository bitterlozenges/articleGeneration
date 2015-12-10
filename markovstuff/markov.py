# -*- coding: utf-8 -*-
from __future__ import division
import re
import sqlite3
from HTMLParser import HTMLParser
from functools import wraps
try:
		import cPickle as pickle
except ImportError:
		import pickle
import logging
import sys
import os
import random
from collections import defaultdict
import nltk
from nltk.tag.perceptron import PerceptronTagger


sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'rake'))
import rake.rake as rake


def genSeeds(text, numSeeds=10, maxWords=3, rake_obj=None):
	""" Returns a list of 'seeds', or keywords from text input.
		args:
			text		 - text input (article)
			numSeeds - number of keywords you want to return
			maxWords - maximum phrase length. default means seeds will be
						 phrases of 3 words or less
				rake_obj - optional RAKE object
			returns:
				list of strings
	"""
	minChars = 5
	minFreq	 = 3

	if not rake_obj:
		rake_obj = rake.Rake("rake/SmartStopList.txt", minChars, maxWords, minFreq)

	keywords = rake_obj.run(text)
	return [s for s, _ in keywords[:numSeeds]]


def genParSeeds(text, numSeeds=10, maxWords=3):
	""" Returns lists of 'seeds', one per paragraph.
		args:
			text		 - text input (article)
			numSeeds - number of keywords you want to return
			maxWords - maximum phrase length. default means seeds will be
						 phrases of 3 words or less
			returns:
				list of lists of strings
	"""
	minChars = 5
	minFreq	 = 1

	paragraphs = text.split("\n")
	rake_obj = rake.Rake("rake/SmartStopList.txt", minChars, maxWords, minFreq)
	return [genSeeds(p, numSeeds, maxWords, rake_obj) for p in paragraphs]


class StringContinuationImpossibleError(Exception):
		pass
		
# {words: {word: prob}}
# We have to define these as separate functions so they can be pickled.
def _db_factory():
		return defaultdict(_one_dict)

def _one():
		return 1.0

def _one_dict():
		return defaultdict(_one)

def _wordIter(text, separator='.'):
		"""
		An iterator over the 'words' in the given text, as defined by
		the regular expression given as separator.
		"""
		exp = re.compile(separator)
		pos = 0
		for occ in exp.finditer(text):
				sub = text[pos:occ.start()].strip()
				if sub:
						yield sub
				pos = occ.start() + 1
		if pos < len(text):
				# take case of the last part
				sub = text[pos:].strip()
				if sub:
						yield sub

class MarkovChain(object):

    def __init__(self, dbFilePath=None, revDbFilePath=None, pos=False):
        self.dbFilePath = dbFilePath
        self.revDbFilePath = revDbFilePath
        if pos:
        	self.tagger = PerceptronTagger()
        self.pos = pos

        # try to open forward database
        if not dbFilePath:
            self.dbFilePath = os.path.join(os.path.dirname(__file__), "markovdb")
        try:
            with open(self.dbFilePath, 'rb') as dbfile:
                self.db = pickle.load(dbfile)
        except (IOError, ValueError):
            logging.warn('Database file corrupt or not found, using empty database')
            self.db = _db_factory()

        # try to open backwards database
        if not revDbFilePath:
            self.revDbFilePath = os.path.join(os.path.dirname(__file__), "revmarkovdb")
        try:
            with open(self.revDbFilePath, 'rb') as dbfile:
                self.rev_db = pickle.load(dbfile)
        except (IOError, ValueError):
            logging.warn('Database file corrupt or not found, using empty database')
            self.rev_db = _db_factory()

    def generateDatabase(self, data, sentenceSep='[.!?\n]', n=2):
        """ Generate word probability database from raw content string 
        args:
            data        - iterator over the rows in the database
            sentenceSep - regular expression detailing possible sentence deliminators
            n           - order of Markov Chain, 
                          i.e. number of preceding words the next word will be based on
        """
        self.db[('',)][''] = 0.0
        # counter to display to user the progress of this function
        z = 0

        for row in data:
            z+=1
            if z%10 == 0:
                print z

            # I'm using the database to temporarily store word counts
            s = strip_tags(row[2])
            the_str = re.sub(ur'[^\w_ .,\’-]+', u' ', s, flags=re.UNICODE)

            if self.pos:
            	rawwords = filter(None,the_str.split(" "))
            	words = map(lambda x: x[1] + "_" + x[0],nltk.tag._pos_tag(rawwords, None, self.tagger))
            	the_str = ' '.join(words)

            textSample = _wordIter(the_str, sentenceSep)  # get an iterator for the 'sentences'
            # We're using '' as special symbol for the beginning
            # of a sentence
            for line in textSample:
                words = line.strip().split()  # split words in line
                if len(words) == 0:
                    continue
                # first word follows a sentence end
                self.db[("",)][words[0]] += 1
                # last word precedes a sentence end
                self.rev_db[("",)][words[-1]] += 1

                # order = order of Markov Chain
                # store order = 1... n data for sentence starting purposes
                for order in range(1, n + 1):
                    # first words follow a sentence end
                    self.rev_db[tuple(words[0:order])][""] += 1

                    for i in range(len(words) - 1):
                        if i + order >= len(words):
                            continue
                        # store forward data
                        prev_words = tuple(words[i:i + order])
                        self.db[prev_words][words[i + order]] += 1

                        # store backwards data
                        next_words = tuple(words[i+1:i+order+1])
                        self.rev_db[next_words][words[i]] += 1

                    # last word precedes a sentence end
                    self.db[tuple(words[len(words) - order:len(words)])][""] += 1
                

        # We've now got the db filled with parametrized word counts
        # We still need to normalize this to represent probabilities
        z=0
        for word in self.db:
            z+=1
            if z%10000 == 0:
                print z
            wordsum = 0
            for nextword in self.db[word]:
                wordsum += self.db[word][nextword]
            if wordsum != 0:
                for nextword in self.db[word]:
                    self.db[word][nextword] /= wordsum

        # normalize reverse 
        z=0
        for word in self.rev_db:
            z+=1
            if z%10000 == 0:
                print z
            wordsum = 0
            for prevword in self.rev_db[word]:
                wordsum += self.rev_db[word][prevword]
            if wordsum != 0:
                for prevword in self.rev_db[word]:
                    self.rev_db[word][prevword] /= wordsum

    def dumpdb(self):
        try:
            print "trying dump"

            with open(self.dbFilePath, 'wb') as dbfile:
                pickle.dump(self.db, dbfile)
            with open(self.revDbFilePath, 'wb') as dbfile:
                pickle.dump(self.rev_db, dbfile)

            # It looks like db was written successfully
            return True
        except IOError:
            logging.warn('Database files could not be written')
            return False

    def generateString(self):
        """ Generate a "sentence" with the database of known text """
        return self._accumulateWithSeed(('',))

    def generateStringWithSeed(self, seed, reverse=False):
        """ Generate a "sentence" with the database and a given word """
        # using str.split here means we're contructing the list in memory
        # but as the generated sentence only depends on the last word of the seed
        # I'm assuming seeds tend to be rather short.
        words = seed.split()
        if (not reverse and (words[-1],) not in self.db) or (reverse and (words[0],) not in self.rev_db):
            # The only possible way it won't work is if the last word is not known
            raise StringContinuationImpossibleError('Could not continue string: '
                                                    + seed)
        return self._accumulateWithSeed(words, reverse)

    def embedStringWithSeed(self, seeda):
        """ Generate a sentence from the front and back. """
        result = ""
        if self.pos:
        	seed = " ".join(map(lambda x: x[1] + "_" + x[0],nltk.tag._pos_tag(nltk.word_tokenize(seeda), None, self.tagger)))
        else:
        	seed = seeda

        result = self.generateStringWithSeed(seed, True)
        if result != "":
        	#if self.pos:
        		#result = result.replace(".","").strip()
        	result += " " + self.generateStringWithSeed(seed)[(len(seeda)+1):]
        	result += ". "

        return result

    def _accumulateWithSeed(self, seed, reverse=False):
        """ Accumulate the generated sentence with a given single word as a
        seed """
        nextWord = self._nextWord(seed, reverse)
        sentence = list(seed) if seed else []
        while nextWord:
            if reverse:
                sentence.insert(0, nextWord)
            else:
                sentence.append(nextWord)
            nextWord = self._nextWord(sentence, reverse)
        if self.pos:
        	return ' '.join(map(lambda x: x.split("_")[-1],sentence)).strip()
        return ' '.join(sentence)

    def _nextWord(self, lastwords, reverse=False):
        db = self.db
        if reverse:
            db = self.rev_db
        lastwords = tuple(lastwords)
        if lastwords != ('',):
            while lastwords not in db:
                if reverse:
                    lastwords = lastwords[:-1]
                else:
                    lastwords = lastwords[1:]
                if not lastwords:
                    return ''
        probmap = db[lastwords]
        sample = random.random()
        # since rounding errors might make us miss out on some words
        maxprob = 0.0
        maxprobword = ""
        for candidate in probmap:
            # remember which word had the highest probability
            # this is the word we'll default to if we can't find anythin else
            if probmap[candidate] > maxprob:
                maxprob = probmap[candidate]
                maxprobword = candidate
            if sample > probmap[candidate]:
                sample -= probmap[candidate]
            else:
                return candidate
        # getting here means we haven't found a matching word. :(
        return maxprobword


class MLStripper(HTMLParser):
		def __init__(self):
				HTMLParser.__init__(self)
				self.reset()
				self.fed = []

		def handle_data(self, d):
				self.fed.append(d)

		def handle_entityref(self, name):
				self.fed.append('&%s;' % name)

		def handle_charref(self, name):
				self.fed.append('&#%s;' % name)

		def get_data(self):
				return ''.join(self.fed)


def _strip_once(value):
		"""
		Internal tag stripping utility used by strip_tags.
		"""
		s = MLStripper()
		try:
				s.feed(value)
		except HTMLParseError:
				return value
		try:
				s.close()
		except HTMLParseError:
				return s.get_data() + s.rawdata
		else:
				return s.get_data()


def strip_tags(value):
		"""Returns the given HTML with all tags stripped."""
		# Note: in typical case this loop executes _strip_once once. Loop condition
		# is redundant, but helps to reduce number of executions of _strip_once.
		while '<' in value and '>' in value:
				new_value = _strip_once(value)
				if len(new_value) >= len(value):
						# _strip_once was not able to detect more tags or length increased
						# due to http://bugs.python.org/issue20288
						# (affects Python 2 < 2.7.7 and Python 3 < 3.3.5)
						break
				value = new_value
		return value

#db to from pos
if sys.argv[1] == "db":
	try:
			con = sqlite3.connect(sys.argv[3])
		
			cur = con.cursor()		
			cur.execute('SELECT * FROM articles')
			the_str = ""
			data = cur.fetchall()
			pos = False
			if len(sys.argv)>4 and sys.argv[4] == "pos":
 				pos = True
			mc = MarkovChain(sys.argv[2]+".forwardb",sys.argv[2]+".backdb",pos)
			mc.generateDatabase(data)
			mc.dumpdb()
			print "Success!"
			
			#print embedStringWithSeed("chocolate")#mc.generateString()

	except sqlite3.Error, e:
		
			print "Error %s:" % e.args[0]
			sys.exit(1)
		
	finally:
		
			if con:
					con.close()
#article db articlefile pos				
elif sys.argv[1] == "article":
 	print "Loading Database"
 	pos=False
 	if len(sys.argv)>4 and sys.argv[4] == "pos":
 		pos = True
	mc = MarkovChain(sys.argv[2]+".forwardb",sys.argv[2]+".backdb",pos)
	while 1 == 1:
			foo=raw_input('Press enter to generate an article based on the article \n')
			sample_file = open(sys.argv[3], 'r')
			txt = sample_file.read()
			paragraphs = genParSeeds(txt)
			for keywords in paragraphs:	 
				fin_str = ""
				for keyword in keywords:
					try:
						fin_str += mc.embedStringWithSeed(keyword)
					except Exception:
						sys.exc_clear()
				print fin_str
				if not (fin_str == ""):
					print "\n"
#test db posdb article
elif sys.argv[1] == "test":
 	print "Loading Database"
	mc = MarkovChain(sys.argv[2]+".forwardb",sys.argv[2]+".backdb",False)
	mcpos = MarkovChain(sys.argv[3]+".forwardb",sys.argv[3]+".backdb",True)
	#keep track of which type article was displayed first
	b = ""
	while 1 == 1:
			
			foo=raw_input('Press enter to generate an article based on the article \n')
			print b #reveal which was which
			sample_file = open(sys.argv[4], 'r')
			txt = sample_file.read()
			paragraphs = genParSeeds(txt)
			#choose a random paragraph
			rand = random.choice(paragraphs)
			a = [mc,mcpos]
			#choose randomly between POS or w/o to display first
			random.shuffle(a)
			m = a[0]
			fin_str = ""
			for keyword in rand:
				try:
					fin_str += m.embedStringWithSeed(keyword)
				except Exception:
					sys.exc_clear()
			print fin_str
			if not (fin_str == ""):
				print "\n"
			m = a[1]
			print "---"
			fin_str = ""
			for keyword in rand:
				try:
					fin_str += m.embedStringWithSeed(keyword)
				except Exception:
					sys.exc_clear()
			print fin_str
			if not (fin_str == ""):
				print "\n"
			if m == mc:
				b = "mcpos/mc"
			else:
				b = "nopos/mcpos"
