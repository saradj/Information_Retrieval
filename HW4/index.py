#!/usr/bin/python3
import getopt
import math
import sys
from collections import defaultdict

import nltk
from nltk.corpus import PlaintextCorpusReader, stopwords
from nltk.stem import PorterStemmer
from nltk.stem.wordnet import WordNetLemmatizer
from nltk.tokenize import RegexpTokenizer, sent_tokenize, word_tokenize

from utils import Entry, Token, PhrasalToken, normalize, get_tf, preprocess
from uk2us import uk2us

import csv
import numpy as np

try:
    import cPickle as pickle
except ImportError:
    import pickle

phrasal_query = True  # operate phrase query

def tokenize(paragraph):
    '''
    Tokenization

    ** remark: the stop word, punctuations and numbers are not removed 
                and are treated as a term in the dictionary
    (1) Do case-folding.
    (2) Remove fullstops by using "sent_tokenize" and "word_tokenize" 
        in the tokenising step.
    '''
    words = [word for sent in sent_tokenize((paragraph.lower()))
             for word in word_tokenize(sent)]

    # tokenizer = nltk.RegexpTokenizer(r"\w+")
    # words = tokenizer.tokenize(text)
    return words


def stemming(words, stopword=True, lemma=True):
    '''
    Do stemming, but the stop word is not removed, and also not do 
    lemmatization.

    @param words: a list of strings
    @return stemmed_tokens: a list of strings
    '''
    ps = PorterStemmer()
    stemmed_tokens = list()  # multiple term entries in a single document are merged
    stem_dict = defaultdict(dict)
    for w in words:

        if w in stem_dict:
            stemmed_tokens.append(stem_dict[w])
            continue
        if stopword:
            stop_words = set(stopwords.words("english"))
        else:  # stopword removal
            stop_words = set()


        if w not in stop_words:
            # stemming
            if lemma:
                # lemmatization
                lem = WordNetLemmatizer()
                token = ps.stem(lem.lemmatize(w, "v"))
            else:
                token = ps.stem(w)
            stemmed_tokens.append(token)
            stem_dict[w] = token
    return stemmed_tokens


def build_index(in_dir, out_dict, out_postings):
    """
    build index from documents stored in the input directory,
    then output the dictionary file and postings file
    """
    print('indexing...')

    ''' read csv files into nest list '''
    maxInt = sys.maxsize
    while True:
        try:
            csv.field_size_limit(maxInt)
            break
        except OverflowError:
            maxInt = int(maxInt/10)

    with open(in_dir, 'r', encoding='UTF-8') as csvfile:
        reader = csv.reader(csvfile)
        rows = [row for row in reader]

    rows.pop(0)

    ''' Load corpus and generate the postings dictionary '''
    postings = defaultdict(dict)
    tokens = list()
    docsInfo = defaultdict(dict)
    # docs_to_terms = defaultdict(dict)
    
    print(str(len(rows)) + " rows in total. ")


    rowID = 1
    consecutive_ids = defaultdict(dict)
    doc_num = 0
    for docID, _, content, date, court in rows:
        if doc_num > 10000:
            break
        consecutive_ids[doc_num] = docID
        docID = doc_num
        doc_num += 1
        print("processing row: " + str(rowID))
        rowID += 1
        docsInfo[docID] = [date, court]
        words = tokenize(uk2us(content))  # tokenization: content -> words
        tokens = stemming(words, stopword=True)  # stemming
        # docs_to_terms[docID] = tokens

        if phrasal_query:
            token_len = defaultdict(list)
        else:
            token_len = defaultdict(int)
        # count the apeearing times of the token in the file
        term_pos = 0
        for token in tokens:
            if phrasal_query:
                if token in token_len.keys():
                    token_len[token][0] += 1
                    token_len[token][1].append(term_pos)
                else:
                    token_len[token] = [1, [term_pos]]
            else:
                token_len[token] += 1

            term_pos += 1

        '''
        Generate weighted token frequency.
        
        Generate dictionary of key -> token, value -> a dict with k,v 
        as file_name, weighted_token_frequency
        '''
        if phrasal_query:

            weighted_tokenfreq = normalize(
                [get_tf(y[0]) for (x, y) in token_len.items()])

            for ((token, freq), w_tf) in zip(token_len.items(), weighted_tokenfreq):
                postings[token][docID] = PhrasalToken(freq[1], w_tf)
        else:

            weighted_tokenfreq = normalize(
                [get_tf(y) for (x, y) in token_len.items()])

            for ((token, freq), w_tf) in zip(token_len.items(), weighted_tokenfreq):
                postings[token][docID] = Token(w_tf)

    ''' 
    Output dictionary and postings files 
    
    - Dictionary file stores all the tokens, with their doc frequency, the offset 
    in the postings file.
    - Postings file stores the list of tuples -> (document ID, term freq).
    '''
    # write postings file
    dictionary = defaultdict(Entry)
    with open(out_postings, mode="wb") as postings_file:
        for key, value in postings.items():
            '''
            len(value) := the document frequency of the token
                       := how many times the token appears in all documents
            offset := current writing position of the postings file
            '''
            offset = postings_file.tell()
            pickle.dump(value, postings_file)
            dictionary[key] = Entry(len(value), offset)

    # write dictionary file
    with open(out_dict, mode="wb") as dictionary_file:

        pickle.dump(len(rows), dictionary_file)
        print("length done.")
        pickle.dump(consecutive_ids, dictionary_file)
        pickle.dump(docsInfo, dictionary_file)
        print("docsInfo done.")
        # pickle.dump(docs_to_terms, dictionary_file)
        # print("docs_to_terms done")
        pickle.dump(dictionary, dictionary_file)
        print("dictionary done")


def usage():
    # command tested on PC:
    # not supporting phrasal query:
    # $ python3 index.py -i /Users/yu/nltk_data/corpora/reuters/training/ -d dictionary.txt -p postings.txt
    # supporting phrasal query:
    # $ python3 index.py -i /Users/yu/nltk_data/corpora/reuters/training/ -d dictionary.txt -p postings.txt -x
    print("usage: " +
          sys.argv[0] + " -i directory-of-documents -d dictionary-file -p postings-file")
    print("tips:\n"
          "  -i  directory of the reuters training data\n"
          "  -d  dictionary file path\n"
          "  -p  postings file path\n"
          "  -x  enable phrasal query\n")


input_directory = output_file_dictionary = output_file_postings = None

try:
    opts, args = getopt.getopt(sys.argv[1:], 'i:d:p:x')
except getopt.GetoptError:
    usage()
    sys.exit(2)

for o, a in opts:
    if o == '-i':  # input directory
        input_directory = a
    elif o == '-d':  # dictionary file
        output_file_dictionary = a
    elif o == '-p':  # postings file
        output_file_postings = a
    elif o == '-x':  # operate phrase query
        phrasal_query = True
    else:
        assert False, "unhandled option"

if input_directory == None or output_file_postings == None or output_file_dictionary == None:
    usage()
    sys.exit(2)

build_index(input_directory, output_file_dictionary, output_file_postings)
