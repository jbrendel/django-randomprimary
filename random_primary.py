"""
A new base class for Django models, which provides them with a better and random
looking primary key for the 'id' field.

This solves the problem of having predictable, sequentially numbered primary keys
for Django models.

Just use 'RandomPrimaryIdModel' as base class for your Django models. That's all.


The generated keys look similar to what you know from URL shorteners. Here are some
examples:

    Ada6z
    UFLX1
    Q68mf
    zjvsx3
    fDXshK
    VNuL0Lp

Each character in the key may be a letter (upper and lower case) or a digit, except
the first chracter, which is always a letter. Therefore, with any additional character
in the key length, the key space increases 62 fold. Just 5 characters already give you
more than 768 million different keys. As the key space gets tighter (can't find unused
key after a few tries), the key length is being increased.

The starting key length and maximum key length are tunable.


License: Use as you wish, for whatever purpose. If you have any improvement or ideas,
         it would be nice if you could share those.

DISCLAIMER: THE WORKS ARE WITHOUT WARRANTY

(c) 2012 Juergen Brendel (http://brendel.com/consulting)

"""

import string
import random

from django.db.utils import IntegrityError
from django.db       import models, transaction

class RandomPrimaryIdModel(models.Model):
    """
    An abstract base class, which provides a random looking primary key for Django models.

    The save() call is pre-processed in order to come up with a different, more random looking
    ID field in order to avoid guessable IDs or the leaking of information to the end user if
    primary keys are ever used in an exposed context. One can always use an internal ID and
    have an additional, random looking exposed ID. But then you'd have to replicate the effort
    anyway, so we may just as well create a properly random looking primary key.

    The performance impact of this doesn't seem to be too bad: We have to call random.choice()
    a couple of times to create a key. If the newly chosen random key does not exist in the
    database then we just save it and are done. Only in case of collision will we have to create
    a new key and retry.

    We retry a number of times, slowly increasing the key length (starting at CRYPT_KEY_LEN_MIN
    and going all the way up to CRYPT_KEY_LEN_MAX). At each key-length stage we try a number
    of times (as many times as the key is long, actually). If we still can't find an unused
    unique key after all those tries we give up with an exception. Note that we do not ex-
    haustively search the key space.

    In reality, getting any sort of collision will be unlikely to begin with. The default
    starting key length of 5 characters will give you more than 768 million unique keys. You
    won't get all of them, but after 5 failed tries, you will jump to 6 characters (now you
    have 62 times more keys to choose from) and likely will quickly find an available key.


    Usage:

    Base your models on RandomPrimaryIdModel, rather than models.Model. That's all.

    Then use CRYPT_KEY_LEN_MIN, CRYPT_KEY_LEN_MAX, KEYPREFIX and KEYSUFFIX in your model's
    class definition to tune the behaviour of the primary key.

    If smaller keys are important to you, decrease the CRYPT_KEY_LEN_MIN value, maybe to
    three. If less retries during possible collisions are important to you and you don't
    mind a few more characters in the key, increase CRYPT_KEY_LEN_MIN and maybe also the
    value for CRYPT_KEY_LEN_MAX.

    Use KEYPREFIX and KEYSUFFIX to specify custom prefixes and suffixes for the key. This
    gives you the option to visually distinguish the keys of different models, if you should
    ever need that. By default, both of those are "".

    Use _FIRSTIDCHAR and _IDCHAR to tune the characters that may appear in the key.

    """
    KEYPREFIX         = ""
    KEYSUFFIX         = ""
    CRYPT_KEY_LEN_MIN = 5
    CRYPT_KEY_LEN_MAX = 9
    _FIRSTIDCHAR      = string.ascii_letters                  # First char: Always a letter
    _IDCHARS          = string.digits + string.ascii_letters  # Letters and digits for the rest

    """ Our new ID field """
    id = models.CharField(db_index    = True,
                          primary_key = True,
                          max_length  = CRYPT_KEY_LEN_MAX+1+len(KEYPREFIX)+len(KEYSUFFIX),
                          unique      = True)

    def __init__(self, *args, **kwargs):
        """
        Nothing to do but to call the super class' __init__ method and initialize a few vars.

        """
        super(RandomPrimaryIdModel, self).__init__(*args, **kwargs)
        self._retry_count = 0    # used for testing and debugging, nothing else

    def _make_random_key(self, key_len):
        """
        Produce a new unique primary key.

        This ID always starts with a letter, but can then have numbers
        or letters in the remaining positions.

        Whatever is specified in KEYPREFIX or KEYSUFFIX is pre/appended
        to the generated key.

        """
        return self.KEYPREFIX + random.choice(self._FIRSTIDCHAR) + \
               ''.join([ random.choice(self._IDCHARS) for dummy in xrange(0, key_len-1) ]) + \
               self.KEYSUFFIX

    @transaction.commit_on_success
    def save(self, *args, **kwargs):
        """
        Modified save() function, which selects a special unique ID if necessary.

        Calls the save() method of the first model.Models base class it can find
        in the base-class list.

        """
        if self.id:
            # Apparently, we know our ID already, so we don't have to
            # do anything special here.
            super(RandomPrimaryIdModel, self).save(*args, **kwargs)
            return

        try_key_len                     = self.CRYPT_KEY_LEN_MIN
        try_since_last_key_len_increase = 0
        while try_key_len <= self.CRYPT_KEY_LEN_MAX:
            # Randomly choose a new unique key
            _id = self._make_random_key(try_key_len)
            try:
                if kwargs is None:
                    kwargs = dict()
                kwargs['force_insert'] = True   # If force_insert is already present in
                                                # kwargs, we want to make sure it's
                                                # overwritten. Also, by putting it here
                                                # we can be sure we don't accidentally
                                                # specify it twice.
                self.id = _id
                super(RandomPrimaryIdModel, self).save(*args, **kwargs)
                break                           # This was a success, so we are done here

            except IntegrityError:              # Apparently, this key is already in use
                self._retry_count += 1
                try_since_last_key_len_increase += 1
                if try_since_last_key_len_increase == try_key_len:
                    # Every key-len tries, we increase the key length by 1.
                    # This means we only try a few times at the start, but then try more
                    # and more for larger key sizes.
                    try_key_len += 1
                    try_since_last_key_len_increase = 0

        else:
            # while ... else (just as a reminder): Execute 'else' if while loop is exited normally.
            # In our case, this only happens if we finally run out of attempts to find a key.
            self.id = None
            raise IntegrityError("Could not produce unique ID for model of type %s" % type(self))

    class Meta:
        abstract = True

